# Migrating from LHTML 2 to LHTML 3

LHTML 3 is a major version: the old conventions are gone, with no
compatibility layer. The [changelog](../CHANGELOG.md) lists every change;
this page is what a caller rewrites.

## Calling LHTML

| LHTML 2 | LHTML 3 |
|---|---|
| `lhtml.run(text, {'line-breaks': True, 'current_directory': d})` | `lhtml.run(text, line_breaks=True)` (named arguments only) |
| macros from the `meta` dict or the front matter | `lhtml.run(text, macros=lhtml.load_macros('macros.yaml'))` |
| `wrap-auto` | `lhtml.wrap(html, title=, css=, js=)` |
| `include::file.html` | include before LHTML (Jinja `{% include %}`): LHTML reads no file |
| `<name>-poster.jpg` found next to a video | `video::clip.mp4{poster="clip.jpg"}` |
| the codec variants of `cache_video_codecs/` | `lhtml.run(text, media=resolver)`, `resolver(src) -> [(url, mime type)]` |

## The source

| LHTML 2 | LHTML 3 |
|---|---|
| `::name[-]`, `::[-]` | `::` |
| `::# comment` | an HTML or Jinja comment |
| `verbatim::[] ... verbatim::[-]` | `code::[text]`, or the raw HTML |
| `$x$`, `$$x$$` | `\(x\)`, `\[x\]` (a `$` is text) |
| a macro's `style:`, `variant: true` | `attrs: 'style="..."'`, `variant: [a, b]` |

## Tags written in Python

A tag returned HTML; it now builds nodes, which `render` writes.

```python
# LHTML 2
def alert(element, context):
    return f'<div class="alert">{element["text"]}</div>'

# LHTML 3
def alert(written):
    return lhtml.Element('div', {'class': 'alert'}, children=[lhtml.Text(written.text)])

lhtml.run(text, tags={'alert': lhtml.Tag(alert)})
```

- `build` receives an `lhtml.Written`: `written.text`, `written.parentheses`,
  `written.brackets`, `written.braces` (the groups as written, which were
  `element['()']`, `['[]']`, `['{}']`), `written.label`, `written.line`...
  `written.attributes` gives the attributes the groups write.
- HTML written as it is is a node too: `lhtml.Raw('<hr>')`. A str is refused.
- A tag that holds what follows until its `::` is
  `lhtml.Tag(build, container=True)`, and builds one `Element`.

## Reading the document tree

`lhtml.parse` then `lhtml.render` is `lhtml.run`; between them, the tree is
yours to read and change ([advanced use](advanced.md#the-document-tree)).

- A node is made as it reads: `Text('a')`, `Element('div', {...}, children=[...])`,
  `Code(body, language)`. `span`, `line`, `column` and `children` are keywords.
- `Element.tag` and `Element.written['()']` are `Element.written.tag` and
  `Element.written.parentheses` (`brackets`, `braces`, `text`);
  `Element.written` is None for an element the caller made.
- `Heading.parentheses`: the `(.class #id)` of a heading as written.
- `Element.closed` is gone: `render` does not read how the source closed an
  element. `Element.end_tag` is False when its closing tag is not written
  (an element still open at the end of the document).
