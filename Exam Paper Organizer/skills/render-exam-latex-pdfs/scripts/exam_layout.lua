local function is_html_marker(raw, marker)
  return raw.format == "html" and raw.text:match(marker) ~= nil
end

local function file_exists(path)
  local handle = io.open(path, "rb")
  if handle then
    handle:close()
    return true
  end
  return false
end

local function normalized_path(path)
  return path:gsub("\\", "/")
end

local function trim_trailing_breaks(inlines)
  while #inlines > 0 do
    local kind = inlines[#inlines].t
    if kind == "SoftBreak" or kind == "LineBreak" or kind == "Space" then
      inlines:remove(#inlines)
    else
      break
    end
  end
end

local function trim_inline_edges(inlines)
  while #inlines > 0 do
    local kind = inlines[1].t
    if kind == "SoftBreak" or kind == "LineBreak" or kind == "Space" then
      inlines:remove(1)
    else
      break
    end
  end
  trim_trailing_breaks(inlines)
end

local function explode_option_markers(inlines)
  local expanded = pandoc.List()
  for _, inline in ipairs(inlines) do
    if inline.t ~= "Str" then
      expanded:insert(inline)
    else
      local text = inline.text
      local cursor = 1
      while cursor <= #text do
        local first, last = text:find("[ABCD]%.", cursor)
        if not first then
          local remainder = text:sub(cursor)
          if remainder ~= "" then
            expanded:insert(pandoc.Str(remainder))
          end
          break
        end
        if first > cursor then
          expanded:insert(pandoc.Str(text:sub(cursor, first - 1)))
        end
        expanded:insert(pandoc.Str(text:sub(first, last)))
        cursor = last + 1
      end
    end
  end
  return expanded
end

local function split_choices(inlines)
  local expanded = explode_option_markers(inlines)
  local question = pandoc.List()
  local choices = {pandoc.List(), pandoc.List(), pandoc.List(), pandoc.List()}
  local expected = 1
  local current = 0
  local labels = {"A.", "B.", "C.", "D."}

  for _, inline in ipairs(expanded) do
    if inline.t == "Str" and expected <= 4 and inline.text == labels[expected] then
      current = expected
      choices[current]:insert(inline)
      expected = expected + 1
    elseif current == 0 then
      question:insert(inline)
    else
      choices[current]:insert(inline)
    end
  end

  if expected ~= 5 then
    return nil
  end
  trim_inline_edges(question)
  for _, choice in ipairs(choices) do
    trim_inline_edges(choice)
  end
  return question, choices
end

local function inlines_to_latex(inlines)
  local rendered = pandoc.write(pandoc.Pandoc({pandoc.Plain(inlines)}), "latex")
  rendered = rendered:gsub("%s+$", "")
  rendered = rendered:gsub("\r?\n", " ")
  return rendered
end

local function choice_command(choices)
  local max_length = 0
  local rendered = {}
  for index, choice in ipairs(choices) do
    local length = pandoc.text.len(pandoc.utils.stringify(choice))
    if length > max_length then
      max_length = length
    end
    rendered[index] = inlines_to_latex(choice)
  end

  local command = "ExamChoicesFour"
  if max_length > 42 then
    command = "ExamChoicesOne"
  elseif max_length > 20 then
    command = "ExamChoicesTwo"
  end
  return string.format("\\%s{%s}{%s}{%s}{%s}", command, rendered[1], rendered[2], rendered[3], rendered[4])
end

local function is_standalone_image(block)
  return (block.t == "Para" or block.t == "Plain")
    and #block.content == 1
    and block.content[1].t == "Image"
end

local function anchor_image_to_previous_question(output, image_block)
  if #output == 0 then
    return false
  end
  local previous = output[#output]
  if previous.t ~= "OrderedList" or #previous.content == 0 then
    return false
  end

  output:remove(#output)

  if #previous.content > 1 then
    local leading_items = pandoc.List()
    for index = 1, #previous.content - 1 do
      leading_items:insert(previous.content[index])
    end
    local leading = pandoc.OrderedList(leading_items)
    leading.start = previous.start
    leading.style = previous.style
    leading.delimiter = previous.delimiter
    output:insert(leading)
  end

  output:insert(image_block)

  local final_item = previous.content[#previous.content]
  for _, item_block in ipairs(final_item) do
    if item_block.t == "RawBlock" and item_block.format == "latex"
      and item_block.text:match("\\ExamChoices") then
      item_block.text = item_block.text
        :gsub("\\ExamChoicesFour", "\\ExamChoicesFigure")
        :gsub("\\ExamChoicesTwo", "\\ExamChoicesFigure")
        :gsub("\\ExamChoicesOne", "\\ExamChoicesFigure")
    end
  end
  local final_items = pandoc.List({final_item})
  local final_list = pandoc.OrderedList(final_items)
  final_list.start = previous.start + #previous.content - 1
  final_list.style = previous.style
  final_list.delimiter = previous.delimiter
  output:insert(final_list)
  return true
end

local function process_blocks(blocks)
  local output = pandoc.List()
  local solution_open = false

  for _, block in ipairs(blocks) do
    if is_standalone_image(block) and anchor_image_to_previous_question(output, block) then
      -- Exam Markdown convention places a diagram immediately after the
      -- question it belongs to. Split the final question from its list and
      -- place the wrapfigure immediately before it. Illustrated choices use
      -- a dedicated narrow measure so they remain readable beside the diagram.
    elseif block.t == "RawBlock" and is_html_marker(block, "exam%-solution:start") then
      if solution_open then
        error("Nested exam-solution start marker")
      end
      output:insert(pandoc.RawBlock("latex", "\\begin{examSolutionBox}"))
      solution_open = true
    elseif block.t == "RawBlock" and is_html_marker(block, "exam%-solution:end") then
      if not solution_open then
        error("exam-solution end marker without a start marker")
      end
      output:insert(pandoc.RawBlock("latex", "\\end{examSolutionBox}"))
      solution_open = false
    elseif block.t == "Para" or block.t == "Plain" then
      local content = pandoc.List()

      local function flush_content()
        trim_trailing_breaks(content)
        if #content > 0 then
          if block.t == "Para" then
            output:insert(pandoc.Para(content))
          else
            output:insert(pandoc.Plain(content))
          end
          content = pandoc.List()
        end
      end

      for _, inline in ipairs(block.content) do
        if inline.t == "RawInline" and is_html_marker(inline, "exam%-solution:start") then
          flush_content()
          if solution_open then
            error("Nested inline exam-solution start marker")
          end
          output:insert(pandoc.RawBlock("latex", "\\begin{examSolutionBox}"))
          solution_open = true
        elseif inline.t == "RawInline" and is_html_marker(inline, "exam%-solution:end") then
          flush_content()
          if not solution_open then
            error("Inline exam-solution end marker without a start marker")
          end
          output:insert(pandoc.RawBlock("latex", "\\end{examSolutionBox}"))
          solution_open = false
        else
          content:insert(inline)
        end
      end
      flush_content()
    elseif block.t == "OrderedList" then
      local segment = pandoc.List()
      local segment_start = block.start

      local function flush_segment()
        if #segment == 0 then
          return
        end
        local split_list = pandoc.OrderedList(segment)
        split_list.start = segment_start
        split_list.style = block.style
        split_list.delimiter = block.delimiter
        output:insert(split_list)
        segment = pandoc.List()
      end

      for item_index, item in ipairs(block.content) do
        local question_number = block.start + item_index - 1
        if question_number == 5 or question_number == 10 or question_number == 16 then
          flush_segment()
          output:insert(pandoc.RawBlock("latex", "\\ExamQuestionPageBreak"))
          segment_start = question_number
        end
        segment:insert(item)
      end
      flush_segment()
    else
      output:insert(block)
    end
  end

  if solution_open then
    error("Unclosed exam-solution marker in a block sequence")
  end
  return output
end

function Blocks(blocks)
  return process_blocks(blocks)
end

function OrderedList(list)
  for item_index, item in ipairs(list.content) do
    local rewritten = pandoc.List()
    for _, block in ipairs(item) do
      if block.t == "Para" or block.t == "Plain" then
        local question, choices = split_choices(block.content)
        if choices then
          if #question > 0 then
            if block.t == "Para" then
              rewritten:insert(pandoc.Para(question))
            else
              rewritten:insert(pandoc.Plain(question))
            end
          end
          rewritten:insert(pandoc.RawBlock("latex", choice_command(choices)))
        else
          rewritten:insert(block)
        end
      else
        rewritten:insert(block)
      end
    end
    list.content[item_index] = rewritten
  end
  return list
end

function Div(div)
  local style = div.attributes["style"] or ""
  if style:match("page%-break%-after%s*:%s*always") then
    return pandoc.RawBlock("latex", "\\clearpage")
  end
  return div
end

function Image(image)
  if image.src:match("^%a+://") or image.src:match("^data:") then
    return image
  end

  for _, root in ipairs(PANDOC_STATE.resource_path or {}) do
    local candidate = pandoc.path.join({root, image.src})
    if file_exists(candidate) then
      image.src = normalized_path(candidate)
      return image
    end
  end

  return image
end

local primary_title = nil
local primary_subject_seen = false
local answer_mode = false

local function normalized_title(title)
  return title:gsub("—", "-"):gsub("–", "-"):gsub("%s+", "")
end

function Header(header)
  local title = pandoc.utils.stringify(header.content)
  local latex_title = inlines_to_latex(header.content)

  if header.level == 2 and primary_title ~= nil and not answer_mode
    and not primary_subject_seen then
    primary_subject_seen = true
    return pandoc.RawBlock("latex", "\\ExamSubjectTitle{" .. latex_title .. "}")
  end

  if header.level ~= 1 then
    return header
  end

  local lowered = title:lower()
  local is_answer_title = lowered:match("参考答案") or lowered:match("answer key") or lowered:match("reference answers")

  if is_answer_title then
    local prefix = ""
    if not answer_mode then
      prefix = "\\beginExamAnswers\n"
      answer_mode = true
    end
    return pandoc.RawBlock("latex", prefix .. "\\ExamAnswerSubjectTitle{" .. latex_title .. "}")
  end

  if primary_title == nil then
    primary_title = title
    return pandoc.RawBlock("latex", "\\ExamMainTitle{" .. latex_title .. "}")
  end

  if normalized_title(title) == normalized_title(primary_title) then
    answer_mode = true
    return pandoc.RawBlock("latex", "\\beginExamAnswers\n\\ExamAnswerMainTitle{" .. latex_title .. "}")
  end

  if answer_mode then
    return pandoc.RawBlock("latex", "\\ExamAnswerSubjectTitle{" .. latex_title .. "}")
  end
  return pandoc.RawBlock("latex", "\\ExamSubjectTitle{" .. latex_title .. "}")
end
