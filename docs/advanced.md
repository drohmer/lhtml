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
it follows). A tag builds the nodes of its element, which `render` writes
as any other:

```python
import lhtml

from lhtml.export_html import element_attributes

def alert(element):
    attributes = element_attributes({**element, '()': '.alert ' + element['()']})   # (.c) [style] {attrs}
    return lhtml.Element(name='div', attributes=attributes, children=[lhtml.Text(value=element['text'])])

html = lhtml.run(text, tags={'alert': lhtml.Tag(alert, container=True)})
```

Then use in LHTML:
```
alert::[background:yellow; padding:10px;] Warning message ::
```

`build(element)` receives what the source wrote: `'tag'` (the name),
`'text'` (the word glued after the groups, without the final `::` of
`name::text::`), `'inline'` (written `name::text::`), `'()'`, `'[]'`,
`'{}'` (the groups as written), `'label'` (the nodes of the `[...]` of a
`link::`, else None), `'line'`, `'column'`, `'context'`. It returns a node,
or a list of nodes: an `Element`, a `Text`, a `Raw` (HTML written as it
is: `lhtml.Raw(text='<hr>')`). A tag that holds what follows until its
`::` says so (`container`: a bool, or a function of the element; written
`name::text::`, it holds nothing either way) and builds one `Element`: what
it holds becomes its children, after those it built. `lhtml.export_html.element_attributes(element)`
gives the attributes the groups write (class and id, style, then `{...}`).
An exception raised by `build` or `container` becomes an `LHTMLError`
naming the tag and its place (the exception as its `__cause__`).

A tag whose text is a URL says so, `lhtml.Tag(build, url=True)`: its URL is
kept as written (`u::a__b.html` is not read as italic), as the ones of the
built-in `link::`, `img::`, `video::`, `videoplay::` and of a macro with
`url:`. A tag given in place of one of them without `url=True` reads its
text as LHTML: write `url=True` when it replaces `img`, for instance.

A tag name starts with a letter, then letters, digits, `_` or `-`; `nl`,
`code` and `include` are LHTML syntax, not tags. A name that is not a tag
stays as text (`std::vector`).

### The document tree

`lhtml.run` is `lhtml.parse` then `lhtml.render`. `render` writes the HTML
from the fields of the nodes alone: change a node, the HTML changes.

```python
document = lhtml.parse('img::before.png and link::page.html[a **link**]')
for node in document.walk():               # headings, lists, bold, italic, elements,
    print(node.kind, node.line, node.column, node.span)     # code, math, raw HTML
image = next(n for n in document.walk() if n.kind == 'Element')
image.attributes['src'] = 'after.png'
html = lhtml.render(document)
```

Every node is an `lhtml.Node`: its `kind` (the name of its class), its
`children`, its place, and `walk()`, the node and its descendants in
document order. The nodes (`lhtml.nodes`) are `Document` (`problems`, `source`), `Heading`
(`level`, `attributes`), `List`, `Item` (a deeper list is a `List` inside
the `Item` before it), `Strong`, `Emphasis`, `Element` (`name`, the HTML
element; `attributes`; `void`: no closing tag; its children), `Video` (an
`Element` with its `src`: its sources are those of the `media` resolver of
`render`), `Text` (`value`, written as it is) and the leaves `Code`
(`language`, `body`), `InlineCode` (`text`), `Math` (`text`, `display`) and
`Raw` (`text`; `raw_kind`: html, comment, script, style, jinja). The label
of a link is its children (`link::u[a **b**]`: a `Text` and a `Strong`);
the word after a tag is its first child (`span::word more ::`: a `Text`
for `word`, then the text that follows).

`attributes` is an `lhtml.Attributes`, a mapping name -> value in order: a
value as in HTML source (a `"` in a value set is written `&quot;`), None
for an attribute without value (`autoplay`); a name is read in any case;
a Jinja fragment written among them (`{% if x %}alt="y"{% endif %}`)
stays in its place, and an expression is part of a name or a value
(`data-{{ k }}="v"`, `title={{ x }}`). Read from the source, an attribute
is written back as written until it is set. The classes of an element and
its style add up, the macro's first (`(.a){class="b"}`: `class="a b"`);
any other attribute is given once, by the last of the tag, the macro, its
`url`, the page (an id written `{id=...}` replaces the one of `(#id)`).

Three fields are information on the source, never read by `render`:
`Element.tag` (the LHTML tag written, `''` for a bare `::`) and
`Element.written` (its groups and word as written: `'()'`, `'[]'`, `'{}'`,
`'text'`; a group across other nodes as written, `**` included), and
`Heading.written`. An element's `closed` says how the source ends it:
`'tag'` (its `::`), `'inline'` (`div::text::`), `'void'` (it holds
nothing), `'container'` (at the end of the heading, item, bold or italic it
is opened in) or `'never'` (not closed: no closing tag is written).

Every node but the document has its place: `span`, the offsets of its source in the text
given to `parse` (end excluded; a `\r\n` or a BOM counted), and `line`,
`column` of its start (1-based); a node a tag built has the place of its
element, a node made by the caller none. `document.problems` holds the
warnings, in source order. The nodes nest, nothing crosses (see the `::`
elements in the [README](../README.md)). The tree is walked and rendered
without recursion: a document may nest deeper than Python's recursion
limit.

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
  __init__.py          # Public API: run, parse, render, wrap, Tag, TAGS, the nodes, LEXERS, macro functions, errors
  __main__.py          # python -m lhtml
  cli.py               # Command-line interface
  pipeline.py          # run(): parse, then render
  tree.py              # parse(): the document tree
  nodes.py             # The nodes of the tree
  render.py            # render(): the HTML of a tree, from its nodes, and its line breaks
  attributes.py        # The attributes: one reader, Attributes, one rule of priority
  diagnostics.py       # The problems as the command shows them
  macros.py            # Macros: custom :: tags declared in YAML
  process.py           # The protected zones, the tag decisions
  patterns.py          # Centralized regex patterns and utilities
  tag_parser.py        # extract_bracket_elements(): the parser of a :: tag element
  export_html.py       # Tag, TAGS: the built-in tags build their nodes
  code.py              # Code syntax highlighting (Pygments)
  wrap_html.py         # HTML document wrapping
  errors.py            # Structured error types
test/                  # pytest suite and .l.html / -out.html reference pairs
examples/              # Example sources (see examples/README.md)
```

Run the tests with `pytest` (after `pip install -e ".[dev]"`).
