# LHTML: advanced use

The [README](../README.md) covers the syntax and `lhtml.run(text)`. This page is for
callers that extend LHTML or read its documents: the macro functions, custom
tags written in Python, the document tree, the lexers, and the layout of the code.

## Macro functions

```python
macros = lhtml.load_macros('macros.yaml')            # definitions from files or dicts
tags = lhtml.registry_with_macros(macros)            # their Tags, validated (LHTMLMacroError)
info = lhtml.describe_macro('box', macros['box'])    # what a definition renders, for docs
```

## Custom tags, the document tree, lexers

### Custom Tags

Give new `::` tags to `lhtml.run`, added to the built-in ones (`lhtml.TAGS`,
a read-only mapping name -> `lhtml.Tag`) and to the macros; a tag given
wins over both, `div` included (the anonymous `::(.c) ... ::` is a div, so
it follows):

```python
import lhtml

def render_alert(element, children, context):
    style = element.get('[]', '')
    return f'<div class="alert" style="{style}">{element["text"]}{children}</div>'

html = lhtml.run(text, tags={'alert': lhtml.Tag(render_alert, container=True)})
```

Then use in LHTML:
```
alert::[background:yellow; padding:10px;] Warning message ::
```

A tag declares whether it holds what follows until its `::` (`container`: a
bool, or a function of the element), so that the parser knows it before
anything is rendered; written `name::text::`, it holds nothing either way
(`element['text']` keeps the final `::`). `render` receives the parsed
element (`'[]'`, `'()'`, `'{}'`, `'text'`: the word glued after the
brackets, `'line'`, `'column'`; `element['closed']` is False when no `::`
closed it), the HTML of what it holds (`''` for a tag that holds nothing)
and the context of the run (`context.media`, `context.line_breaks`; an
option of the tag itself is in its closure), and returns
its HTML, closing tag included, as a `str`. An exception raised by `render`
or `container` becomes an `LHTMLError` naming the tag and its place (the
exception as its `__cause__`).

A tag whose text is a URL says so, `lhtml.Tag(render, url=True)`: its URL is
kept as written (`u::a__b.html` is not read as italic), as the ones of the
built-in `link::`, `img::`, `video::`, `videoplay::` and of a macro with
`url:`. A tag given in place of one of them without `url=True` reads its
text as LHTML: write `url=True` when it replaces `img`, for instance.

A tag name starts with a letter, then letters, digits, `_` or `-`; `nl`,
`code` and `include` are LHTML syntax, not tags. A name that is not a tag
stays as text (`std::vector`).

### The document tree (experimental)

`lhtml.run` is `lhtml.parse` then `lhtml.render`. The tree is **experimental
in 3.0**: read it to inspect a document (its nodes and their places), do not
edit it to change the HTML - `render` reads the internal copies of the nodes
(`Text.raw`, the element a tag receives, the stores of the zones), not
`Text.value`, `Element.value` or `Code.body`. Its shape may change in a
minor version (a link label as nodes, the public fields read by `render`).

```python
document = lhtml.parse(text, macros=...)   # headings, lists, bold, italic, :: elements,
for node in document.walk():               # and code, inline code, math, raw HTML as leaves
    print(node.kind, node.line, node.column, node.span)
html = lhtml.render(document)
```

The nodes are `Document`, `Heading` (`level`, `attributes`), `List`,
`Item` (a deeper list is a `List` inside the `Item` before it), `Strong`,
`Emphasis`, `Element` (`name`, '' for an anonymous `::`; `groups`; `value`;
`closed`), `Text` (`value`) and the leaves `Code` (`language`, `body`),
`InlineCode`, `Math` and `Raw` (`text`; `raw_kind`: html, comment, script,
style, jinja). The groups and the value of an element, and the attributes of a heading, are as written (Jinja and mathematics included); the label of a `link::` (`groups['[]']`) holds its bold and italic as HTML (`<strong>`), the rest as written.

Every node has its place: `span`, the offsets of its source in the text
given to `parse` (end excluded; a `\r\n` or a BOM counted), and `line`,
`column` of its start (1-based). The children of a node lie within its span
and in order. `document.problems` holds the warnings, in source order.

The nodes nest, nothing crosses (see the `::` elements in the [README](../README.md)). An element's
`closed` says how it ends: `'tag'` (its `::`), `'inline'` (`div::text::`),
`'void'` (it holds nothing), `'container'` (at the end of the heading,
item, bold or italic it is opened in) or `'never'` (no closing tag). The
tree is walked and rendered without recursion: a document may nest deeper
than Python's recursion limit.

### Custom Code Lexers

`lhtml.LEXERS` maps a language name to a Pygments lexer class, looked up
before the lexers of Pygments:

```python
import lhtml
from pygments.lexers import PythonLexer

lhtml.LEXERS['mypython'] = PythonLexer
```


## Layout of the code

```
src/lhtml/
  __init__.py          # Public API: run, parse, render, Tag, TAGS, LEXERS, macro functions, errors
  __main__.py          # python -m lhtml
  cli.py               # Command-line interface
  pipeline.py          # run(): parse, then render
  tree.py              # The document tree: parse() and render()
  macros.py            # Macros: custom :: tags declared in YAML
  process.py           # The protected zones, the tag decisions, line breaks
  patterns.py          # Centralized regex patterns and utilities
  tag_parser.py        # extract_bracket_elements(): the parser of a :: tag element
  export_html.py       # Tag, TAGS and the HTML of the built-in tags
  code.py              # Code syntax highlighting (Pygments)
  wrap_html.py         # HTML document wrapping
  errors.py            # Structured error types
test/                  # pytest suite and .l.html / -out.html reference pairs
examples/              # Example sources (see examples/README.md)
```

Run the tests with `pytest` (after `pip install -e ".[dev]"`).
