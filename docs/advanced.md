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

def alert(written):
    attributes = written.attributes.add_class('alert')     # (.c) [style] {attrs}, and the class alert
    return lhtml.Element('div', attributes, children=[lhtml.Text(written.text)])

html = lhtml.run(text, tags={'alert': lhtml.Tag(alert, container=True)})
```

Then use in LHTML:
```
alert::[background:yellow; padding:10px;] Warning message ::
```

`build(written)` receives what the source wrote, an `lhtml.Written`
(read-only): `tag` (the name), `text` (the word glued after the groups,
without the final `::` of `name::text::`), `inline` (written
`name::text::`), `parentheses`, `brackets`, `braces` (the groups `(...)`,
`[...]`, `{...}` as written), `label` (the nodes of the `[...]` of a
`link::`: its text, bold, italic, and the elements that hold nothing, an
`img::` among them; else None), `line`, `column`, `context` (what a message quotes).
`written.attributes` is a new `Attributes` each time: those the groups
write, class and id, style (not for `link::`, whose `[...]` is its label),
then `{...}`.

`build` returns a node, or a list of nodes: an `Element`, a `Text`, a `Raw`
for HTML written as it is (`lhtml.Raw('<hr>')`); a str is refused. A tag
that holds what follows until its `::` says so (`container`: a bool, or a
function of the Written; written `name::text::`, it holds nothing either
way) and builds one `Element`: the parser puts what it holds in its
children, after those it built. An exception raised by `build` or
`container` becomes an `LHTMLError` naming the tag and its place (the
exception as its `__cause__`).

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
document order. A node is made as it reads, its place and children as
keywords:

```python
note = lhtml.Element('div', {'class': 'note'}, children=[lhtml.Strong(children=[lhtml.Text('Important')])])
lhtml.render(note)          # '<div class="note"><strong>Important</strong></div>'
```

The nodes (`lhtml.nodes`) are `Document` (`problems`, `source`), `Heading`
(`level`, `attributes`), `List`, `Item` (a deeper list is a `List` inside
the `Item` before it), `Strong`, `Emphasis`, `Element` (`name`, the HTML
element; `attributes`; `void`: no content nor closing tag; `end_tag`:
False when its closing tag is not written, an element still open at the
end of the document (one the end of a heading, an item, a bold or an
italic closes gets it); its children), `Video` (an `Element` with its
`src`, `Video('clip.mp4')`: its sources are those of the `media` resolver
of `render`), `Text` (`value`, written as
it is) and the leaves `Code` (`body`, `language`), `InlineCode` (`text`),
`Math` (`text`, `display`) and `Raw` (`text`; `raw_kind`: html, comment,
script, style, jinja). The label of a link is its children
(`link::u[a **b**]`: a `Text` and a `Strong`); the word after a tag is its
first child (`span::word more ::`: a `Text` for `word`, then the text that
follows). The text of an `a` element of the tree (`link::`, a
macro of tag `a`) is one label: with `line_breaks`, its line breaks are not
made visible (raw HTML `<a>` is text: its line breaks are).

`attributes` is an `lhtml.Attributes` (a dict given is made one), a
mapping name -> value in order: a value as in HTML source (a `"` in a
value set is written `&quot;`), None for an attribute without value
(`autoplay`); a name is read in any case, its Jinja as written
(`data-{{ K }}` is not `data-{{ k }}`); a Jinja fragment written among them
(`{% if x %}alt="y"{% endif %}`) stays in its place, and an expression is
part of a name or a value (`data-{{ k }}="v"`, `title={{ x }}`). Read from
the source, an attribute is written back as written until it is set.
`copy()`, `without(names)` and `extend(other)` give or change Attributes
without touching the other one; `add_class('a b', 'c')` adds classes to its
class, once each. The classes of an element and its style
add up, a macro's first (`(.a){class="b"}`: `class="a b"`; an empty one
joins the others, `(.a){class=""}` is `class="a"`, and alone it is kept,
in the page as in the `attrs` of a macro); one written inside a Jinja block
(`{% if x %}class="a"{% endif %}`) stays in it, as written;
any other attribute is given once, by the last of the tag, the macro, its
`url`, the page (an id written `{id=...}` replaces the one of `(#id)`).

What the source wrote is information, never read by `render`:
`Element.written`, the `Written` its tag was given (None for an element the
caller made, and for one a tag made inside the nodes it returns;
`written.label` is the link's children, the same nodes: `written.tag` is the LHTML tag, `''` for a bare `::`; a group
across other nodes is as written, `**` included), and `Heading.parentheses`,
its `(.class #id)` as written.

Every node but the document has its place: `span`, the offsets of its source in the text
given to `parse` (end excluded; a `\r\n` or a BOM counted), and `line`,
`column` of its start (1-based); a node a tag built has the place of its
element, a node made by the caller none. `document.problems` holds the
problems, in source order (`parse(text, warn=False)`: kept, not warned). The nodes nest, nothing crosses (see the `::`
elements in the [README](../README.md)). The tree is walked and rendered
without recursion: a document may nest deeper than Python's recursion
limit, whatever its nodes.

### Reading a source as LHTML reads it

A tool around LHTML (a site generator's lint, a source map, a plugin) may
need to agree with it on what is code and what is text, without parsing:

```python
for zone in lhtml.zones(text):          # in order, one left-to-right pass
    zone.kind                           # code, jinja, comment, raw, inline_code, url, math, tag
    text[zone.start:zone.end]
    zone.tag, zone.value                # a url zone: img, a.png

for found in lhtml.read_tags(text, macros=macros):     # the tags parse reads, in order
    found.start, found.end, found.written              # text[start:end], what it writes
found = lhtml.read_tag(text, start)                    # the syntax written at `start`
found.written.braces                                   # its {...} as written
```

`zones` reads with the patterns of `parse`, and ends a URL where it does
(`**img::a.png**`: `a.png`). It takes `url_tags` (the tags whose text is
a URL: the built-in ones, `lhtml.URL_TAGS`; add the macros with `url:`),
`code` (the pattern of the code blocks of another markup, the fenced
blocks of Markdown, in place of `code::[...]`) and `start`.

`read_tags` gives the tags `parse` reads: `parse` notes each one as it
reads it, with its own rules, so a tool agrees with LHTML on every tag
(none in a code block, a comment, inline code or a URL; a URL whole,
`img::{{ base }}/a.png`, and ending before the `**` that closes a bold;
the tags in a link's label, but a container there, which is text). It
takes the `tags` and `macros` of the run, as `parse` does (a tag of a
tool: `tags={'includeadv': lhtml.Tag(build)}`), and `names`, a filter:
those tags only, what is read does not change. Each `SourceTag(start,
end, written)`: the tag at `text[start:end]` (a tag that holds what
follows: its opening), `written` as its `Tag` got it (tag, text, groups
as written, line, column, context; a link's label, its nodes). Each call
reads anew: what it gives is the caller's.

`read_tag` reads the syntax written at a place, any name, wherever it is,
the text as it is: what a plugin replaces before LHTML reads the page (a
tag of its own, in a code block too). No markup around it is read: in
`**img::a.png**` its URL is `a.png**` (`read_tags` gives `a.png`). Its
groups, its URL whole for a tag of `url_tags`, no label. A page read tag
by tag stays linear (its brackets and lines are read once per text). A
`start` outside the text is a `ValueError`; a name that does not start
there (`pan::` in `span::`) gives `None`.

### Custom Code Lexers

A call may name its own languages, `{name: Pygments lexer class}`, looked
up before `lhtml.LEXERS`, then the lexers of Pygments; no other call sees
them:

```python
import lhtml
from pygments.lexers import PythonLexer

html = lhtml.run(text, lexers={'mypython': PythonLexer})
document = lhtml.parse(text, lexers=lexers)            # a language they know is no warning
html = lhtml.render(document, lexers=lexers)           # and it is highlighted with them
```

`lhtml.LEXERS` is the table of every call (`c++`: C++ with the types of
the CGP library); adding to it changes all the calls of the process.


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
  process.py           # The protected zones (placeholders), the syntax removed in 3.0
  patterns.py          # Centralized regex patterns and utilities
  tag_parser.py        # The parser of a :: tag element, and whether a :: is a tag
  tags.py              # Tag, TAGS: the built-in tags build their nodes
  code.py              # Code syntax highlighting (Pygments)
  wrap_html.py         # HTML document wrapping
  errors.py            # The errors, the warnings, how a parse collects its problems
test/                  # pytest suite and .l.html / -out.html reference pairs
examples/              # Example sources (see examples/README.md)
```

Run the tests with `pytest` (after `pip install -e ".[dev]"`).
