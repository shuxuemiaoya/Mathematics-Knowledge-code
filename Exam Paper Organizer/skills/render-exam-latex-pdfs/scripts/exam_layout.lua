local function is_html_marker(raw, marker)
  return raw.format == "html" and raw.text:match(marker) ~= nil
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

local function process_blocks(blocks)
  local output = pandoc.List()
  local solution_open = false

  for _, block in ipairs(blocks) do
    if block.t == "RawBlock" and is_html_marker(block, "exam%-solution:start") then
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

function Div(div)
  local style = div.attributes["style"] or ""
  if style:match("page%-break%-after%s*:%s*always") then
    return pandoc.RawBlock("latex", "\\clearpage")
  end
  return div
end

function Header(header)
  if header.level == 1 then
    local title = pandoc.utils.stringify(header.content):lower()
    if title:match("参考答案") or title:match("answer key") or title:match("reference answers") then
      return {header, pandoc.RawBlock("latex", "\\useExamPageStyle")}
    end
  end
  return header
end
