"""Failure injection for concurrent edits, process leases and concept linking."""
import copy
import contextlib
import io
import json
import os
import socket
import unittest
from unittest.mock import patch

import test_pipeline_integrity as base
import book_graph_transaction as transaction


class RecoveryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.f = base.IntegrityTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_relative_links_and_shared_sentence_anchors(self):
        source, coverage, candidates, manifest = self.f.concept_fixture()
        sentence = "我们把研究对象统称为元素，把一些元素组成的总体叫做集合。"
        source.write_text("# 定义\n\n" + sentence + "\n")
        payload = json.loads(candidates.read_text())
        first = payload["concepts"][0]
        first.update(source_note_sha256=base.runtime.sha256_file(source), anchor_text=sentence)
        payload["concepts"].insert(0, {**first, "name": "元素", "link_text": "元素", "anchor_text": "研究对象统称为元素"})
        base.dump(candidates, payload)
        self.f.profile["links"]["note_mode"] = "relative"
        base.dump(self.f.profile_path, self.f.profile)
        base.concepts.apply_candidates(self.f.profile_path, coverage, candidates, manifest)
        self.assertIn("统称为[元素](../概念/元素.md)", source.read_text())
        self.assertIn("叫做[集合](../概念/集合.md)", source.read_text())
        self.assertIn("[定义](../内容/定义.md)", (self.f.book / "概念/集合.md").read_text())

    def test_overlapping_defining_terms_fail_before_writes(self):
        source, coverage, candidates, manifest = self.f.concept_fixture()
        payload = json.loads(candidates.read_text())
        payload["concepts"].append({**payload["concepts"][0], "name": "集合的别名"})
        base.dump(candidates, payload)
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "overlapping"):
            base.concepts.apply_candidates(self.f.profile_path, coverage, candidates, manifest)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.f.book / "概念").exists())

    def test_edit_between_planning_and_commit_is_not_overwritten(self):
        source, coverage, candidates, manifest = self.f.concept_fixture()
        commit = base.concepts.commit_transaction
        edited = source.read_text() + "人工补充\n"
        def edit_then_commit(*args, **kwargs):
            source.write_text(edited)
            return commit(*args, **kwargs)
        with patch.object(base.concepts, "commit_transaction", side_effect=edit_then_commit):
            with self.assertRaisesRegex(ValueError, "input drift"):
                base.concepts.apply_candidates(self.f.profile_path, coverage, candidates, manifest)
        self.assertEqual(source.read_text(), edited)
        self.assertFalse((self.f.book / "概念/集合.md").exists())
        self.assertFalse(manifest.exists())

    def test_reused_concept_is_guarded_during_recovery(self):
        source, coverage, candidates, manifest = self.f.concept_fixture()
        target = self.f.book / "概念/集合.md"
        target.parent.mkdir()
        target.write_text("# 集合\n\n来源：[定义](/演示书/内容/定义.md)\n\n## 定义\n\n总体叫做集合。\n")
        payload = json.loads(candidates.read_text())
        payload["concepts"][0]["existing_target_sha256"] = base.runtime.sha256_file(target)
        base.dump(candidates, payload)
        with patch.object(base.concepts, "atomic_write", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                base.concepts.apply_candidates(self.f.profile_path, coverage, candidates, manifest)
        target.write_text(target.read_text() + "人工补充\n")
        with self.assertRaisesRegex(ValueError, "input drift"):
            base.concepts.apply_candidates(self.f.profile_path, coverage, candidates, manifest)
        self.assertNotIn("[集合]", source.read_text())

    def test_active_process_blocks_complete_restart_and_upstream_invalidation(self):
        state = base.runtime.init_state(self.f.profile_path)
        stage = base.runtime.begin_stage(state, "markdown-registration", [])
        stage["execution"] = {"host": socket.gethostname(), "pid": os.getpid()}
        snapshot = copy.deepcopy(state)
        with self.assertRaisesRegex(base.runtime.PipelineError, "still running"):
            base.runtime.complete_stage(state, "markdown-registration", [("file", self.f.source)])
        self.assertEqual(state, snapshot)
        # Even a failed status must not discard an active worker's lease.
        stage["status"] = "failed"
        with self.assertRaisesRegex(base.runtime.PipelineError, "still running"):
            base.runtime.begin_stage(state, "markdown-registration", [])
        stage["status"] = "running"
        missing = self.f.stage / "missing.json"
        state["stages"][0]["outputs"].append({"kind": "file", "path": str(missing), "sha256": "0" * 64})
        snapshot = copy.deepcopy(state)
        with self.assertRaisesRegex(base.runtime.PipelineError, "still running"):
            base.runtime.validate_resume(state)
        self.assertEqual(state, snapshot)

    def test_dead_process_lease_can_be_recovered(self):
        state = base.runtime.init_state(self.f.profile_path)
        stage = base.runtime.begin_stage(state, "markdown-registration", [])
        stage["execution"] = {"host": socket.gethostname(), "pid": 99999999}
        with patch.object(base.runtime.os, "kill", side_effect=ProcessLookupError):
            base.runtime.validate_resume(state)
        self.assertEqual(stage["status"], "failed")
        self.assertNotIn("execution", stage)

    def test_windows_liveness_does_not_send_a_signal(self):
        with patch.object(base.runtime.sys, "platform", "win32"), \
             patch.object(base.runtime, "windows_process_is_alive", return_value=True) as query, \
             patch.object(base.runtime.os, "kill") as signal:
            self.assertTrue(base.runtime.process_is_alive(123))
        query.assert_called_once_with(123)
        signal.assert_not_called()

    def test_publication_lock_blocks_a_second_writer(self):
        journal = self.f.stage / "transaction.json"
        target = self.f.book / "note.md"
        with transaction.publication_lock(journal):
            with self.assertRaisesRegex(ValueError, "already in progress"):
                transaction.commit_transaction(journal, {"run": "one"}, [(target, "body")])
        transaction.commit_transaction(journal, {"run": "one"}, [(target, "body")])
        self.assertEqual(target.read_text(), "body")

    def test_each_target_is_rechecked_before_its_write(self):
        one, two = self.f.root / "one.md", self.f.root / "two.md"
        one.write_text("one")
        two.write_text("two")
        journal = self.f.stage / "transaction.json"
        def racing_writer(path, text):
            transaction.atomic_write(path, text)
            if path == one:
                two.write_text("manual edit")
        with self.assertRaisesRegex(ValueError, "target drift"):
            transaction.commit_transaction(journal, {"run": "one"}, [(one, "new one"), (two, "new two")], writer=racing_writer)
        self.assertEqual(two.read_text(), "manual edit")

    def test_unmanaged_notes_block_formatting_and_metadata_before_writes(self):
        self.f.split_book()
        foreign = self.f.book / "answers/Q1.md"
        foreign.parent.mkdir()
        foreign.write_text("---\nanswer_for: Q1\n---\n> [!faq] 答案\n> D\n")
        before = base.corpus_snapshot(self.f.book)
        with self.assertRaisesRegex(ValueError, "ownership mismatch"):
            base.markdown.run(self.f.profile_path, self.f.stage / "format.json")
        with self.assertRaisesRegex(ValueError, "ownership mismatch"):
            base.metadata.process_book_metadata(self.f.book, self.f.profile_path, self.f.stage / "metadata.json")
        self.assertEqual(base.corpus_snapshot(self.f.book), before)

    def test_formatting_and_metadata_preserve_edits_made_during_preparation(self):
        self.f.split_book()
        target = self.f.book / "内容/条件.md"
        original = target.read_text()
        for owner in (base.markdown, base.metadata):
            with self.subTest(stage=owner.__name__):
                target.write_text(original)
                publisher = owner.guarded_write_batch
                def edit_then_publish(*args, **kwargs):
                    target.write_text(original + "人工补充\n")
                    return publisher(*args, **kwargs)
                with patch.object(owner, "guarded_write_batch", side_effect=edit_then_publish):
                    with self.assertRaisesRegex(ValueError, "input drift"):
                        if owner is base.markdown:
                            owner.run(self.f.profile_path, self.f.stage / "format.json")
                        else:
                            owner.process_book_metadata(self.f.book, self.f.profile_path, self.f.stage / "metadata.json")
                self.assertEqual(target.read_text(), original + "人工补充\n")

    def test_reviewed_repair_does_not_overwrite_a_late_edit(self):
        self.f.split_book()
        target = self.f.book / "内容/条件.md"
        recipe = self.f.stage / "repairs.json"
        report = self.f.stage / "repair-report.json"
        before = target.read_text()
        base.dump(recipe, {"profile": str(self.f.profile_path), "source_sha256": self.f.profile["source"]["sha256"],
            "reviewer_confirmed": True, "repairs": [{"path": "内容/条件.md", "before_sha256": base.runtime.sha256_file(target),
            "operation": "replace-text", "old": "若", "new": "如果", "reason": "edition correction", "evidence": "reviewed page 1"}]})
        commit = base.repairs.commit_transaction
        def edit_then_commit(*args, **kwargs):
            target.write_text(before + "人工补充\n")
            return commit(*args, **kwargs)
        argv = ["repair", str(self.f.profile_path), str(recipe), str(report), "--reviewer-confirmed"]
        with patch.object(base.repairs.sys, "argv", argv), \
             patch.object(base.repairs, "commit_transaction", side_effect=edit_then_commit), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "input drift"):
                base.repairs.main()
        self.assertEqual(target.read_text(), before + "人工补充\n")
        self.assertFalse(report.exists())

    @unittest.skipIf(os.name == "nt", "symlink privilege is environment-dependent on Windows")
    def test_redirected_parent_path_blocks_recovery(self):
        parent = self.f.root / "owned"
        parent.mkdir()
        target = parent / "note.md"
        target.write_text("original")
        journal = self.f.stage / "transaction.json"
        with self.assertRaises(OSError):
            transaction.commit_transaction(journal, {}, [(target, "replacement")], writer=lambda p, t: (_ for _ in ()).throw(OSError("injected")))
        moved = self.f.root / "moved"
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "redirected"):
            transaction.resume_transaction(journal, {})
        self.assertEqual((moved / "note.md").read_text(), "original")


if __name__ == "__main__":
    unittest.main()
