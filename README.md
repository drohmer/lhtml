# LHTML — Lightweight HTML

[![Tests](https://github.com/drohmer/lhtml/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/drohmer/lhtml/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/lhtml-markup)](https://pypi.org/project/lhtml-markup/)

LHTML is a markup language that simplifies HTML authoring with embedded CSS styling. It is designed to be **HTML-first**: raw HTML passes through untouched, and only a few shorthand symbols (`::`, `*`, `=`, `**`, `__`) trigger conversions.

LHTML is used to build static websites and presentation slides, typically combined with Jinja2 templates.

See the [examples](https://github.com/drohmer/lhtml/tree/main/examples/) and the [changelog](https://github.com/drohmer/lhtml/blob/main/CHANGELOG.md).

## Installation

From PyPI:

```bash
pip install lhtml-markup
```

Or from source:

```bash
git clone https://github.com/drohmer/lhtml.git
cd lhtml
pip install .
```

For development:

```bash
pip install -e ".[dev]"
```

Dependencies (`pygments`, `pyyaml`) are installed automatically.


## In two minutes

```
= Title                          <h1>Title</h1>
== Section                       <h2>Section</h2>
* item                           a list (** for a nested one)
**bold** and __italic__          <strong>bold</strong> and <em>italic</em>
`code`                           inline code, never read as LHTML
link::https://example.org[text]  <a href="https://example.org">text</a>
img::photo.jpg[width:300px;]     <img style="width:300px;" ...>
div::(.note)[color:gray;]        a block with a class and a style ...
Some text                        ... that holds what follows ...
::                               ... until its ::
code::[python]                   a highlighted code block, until code::[-]
x = 1
code::[-]
<b>raw HTML</b>                  kept as it is; so are \(math\) and {{ jinja }}
```

```bash
lhtml page.l.html                # the HTML on stdout
lhtml page.l.html -o page.html   # to a file
```

```python
import lhtml
html = lhtml.run(text)
```

The rest of this page details each construct; [docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md)
is for callers that extend LHTML in Python.


## Quick Start

### Command Line

```bash
lhtml input.l.html                    # Convert to stdout
lhtml input.l.html -o output.html     # Convert to file
lhtml input.l.html -w                 # Wrap in full HTML document (--wrap)
lhtml input.l.html -b                 # Render source line breaks as <br> (--line-breaks)
lhtml input.l.html -m macros.yaml     # Declare macros, custom :: tags (--macros)
lhtml a.l.html b.l.html               # Several files: a.html, b.html next to sources
lhtml a.l.html b.l.html -o build/     # Several files into a directory
lhtml a.l.html b.l.html -o build/ -v  # ... naming each file written (-q: no summary)
python -m lhtml input.l.html          # Alternative invocation
lhtml --version                       # Show the version (also lhtml.__version__)
```

Without `-o`, one input is written to stdout, and several inputs are each
written next to their source (`page.l.html` to `page.html`). With `-o`, one
input is written to that file, several into that directory; two inputs that
would be written to the same file are refused before anything is written.

- stdout holds the HTML only, stderr every message: `lhtml page.l.html > page.html` writes a clean file.
- The destinations are checked before any file is written: an input missing, two inputs written to one file (or to names that differ by case only, or to two names of one file), an output that is an input (or a symbolic or hard link to one), an output under a file: an error each, and nothing is written.
- Then each file is converted and written; one that fails does not stop the others. Writing files ends with a summary (`2 converted · 1 warning`).
- Exit status: 0; 1 when a file is not converted or not written; 2 for a wrong use of the command.
- Files are read and written as UTF-8 (a BOM is accepted).
- LHTML reads no file but its input and the macro files given with `--macros`, and no front matter: its options come from the command line, or from the caller of `lhtml.run()`.

A problem is one line, `file:line:column: level: message`, which editors and
terminals recognize. In a terminal, the line of the source follows, the
place underlined, and the level is colored (never only colored: it is
written; `NO_COLOR` turns colors off, `FORCE_COLOR` on):

```
page.l.html:3:1: warning: div:: is never closed
  3 │ div::(.note)
    │ ^^^^^^^^^^^^

2 converted · 1 warning
```

Without a terminal (a log, an editor), the same problem is one line, its
quote included: `page.l.html:3:1: warning: div:: is never closed (near 'div::(.note)')`.

With `-w`, the result is wrapped in a minimal HTML document, `lhtml.wrap` (title `Webpage`, no CSS or JS from the command line). From Python, `lhtml.wrap(html, title='My Page', css=['style.css'], js=['app.js'])` gives:

```html
<!DOCTYPE html>

<html lang="en">

<head>
	<meta charset="utf-8">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<title>My Page</title>
	<link rel="stylesheet" type="text/css" href="style.css">
	<script src="app.js" defer></script>
</head>

<body>
<h1>Hello</h1>


</body>

</html>
```

### Python API

```python
import lhtml

html = lhtml.run('= Hello World\nSome **bold** text.\n')

html = lhtml.run(text,
                 macros={'box': {'class': 'box'}},    # custom :: tags, see Macros below
                 line_breaks=True)                    # source line breaks as <br>

page = lhtml.wrap(html, title='My Page', css=['style.css'], js=['script.js'])
```

That is the whole API of a page. Custom tags written in Python, the macro
functions and the document tree are in [docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md).
Coming from LHTML 2: [docs/migration.md](https://github.com/drohmer/lhtml/blob/main/docs/migration.md).


## Syntax Reference

### Headings

```
= Main Title
== Subtitle
=== Level 3
```

Output:
```html
<h1>Main Title</h1>
<h2>Subtitle</h2>
<h3>Level 3</h3>
```

With classes/IDs:
```
=(.highlight #intro) Styled Title
```
```html
<h1 class="highlight" id="intro">Styled Title</h1>
```


### Lists

```
* First item
* Second item
** Nested item
* Back to top level
```

Output (a nested list is inside the item before it):
```html
<ul>
<li>
First item
</li>
<li>
Second item
<ul>
<li>
Nested item
</li>
</ul>
</li>
<li>
Back to top level
</li>
</ul>
```

Each `*` adds one level (`***` is level 3). A list ends at the first line that is not an item. A nested list with no item before it to hold it (a list that starts at `**`, or a jump of two levels) gets an item of its own.


### Inline Formatting

```
This is **bold** text.
This is __italic__ text.
This is `inline code` text.
```

Output:
```html
This is <strong>bold</strong> text.
This is <em>italic</em> text.
This is <code class="code-inline">inline code</code> text.
```

A bold and an italic nest, they do not cross: in `**b __c** d__` the italic is left as text, with a warning.

Inline code is literal: `<` and `>` are escaped (so `` `std::vector<float>` `` displays correctly), and nothing in it is interpreted - not `**`, `__`, `code::`, nor any tag (`` `link::x` `` stays text; write `<code class="code-inline">link::url[name]</code>` for a link in code). Existing entities such as `&lt;` are kept.


### Tag Elements (the `::` system)

The core of LHTML. The general syntax is:

```
tagName::(.classes #id)[cssStyle]{htmlAttributes} content ::
```

All bracket groups are optional. If `tagName` is omitted, defaults to `div`.

Tag names start with a letter and may contain letters, digits, `_` and `-` (useful for custom tags). A tag is only recognized when it is not glued to a preceding word: `std::chrono::seconds`, `obj.link::x` or the Python slice `a[::2]` are left untouched.

A closing `::` may be directly followed by punctuation or HTML (`**span::[c] x ::**`, `important ::,`). A marker is exactly two colons: a run of three or more (`:::`, `::::`) is text. A `::` between two HTML tags (as in pre-highlighted code `<span>::</span>`) is left untouched.

A tag that is opened but never closed, or a `::` that closes nothing, produces an `LHTMLWarning` quoting the beginning of the tag. An unmatched `::` is kept as text in the output.

Elements nest inside headings, list items, bold and italic: one opened there and not closed there is closed at its end, with a warning, and a `::` closes the last open element only when both are in the same heading, item, bold or italic (or both outside). In `div:: a **x :: y** b ::` the `::` inside the bold closes nothing (a warning, it stays as text) and the last one closes the div. A `link::` whose label would cross the end of a heading, an item or a bold (`**x link::u[b** c]`) is left as text, with a warning.

A warning or an error has the `line` and `column` where it is in the text given to `lhtml.run` (`None` when not known). The command line prints each problem as `file:line:column: level: message`.

#### Div / Span with Styles

```
div::[color:red; font-size:120%;]
This text is big and red.
::

span::(.highlight)[font-weight:bold;] inline content ::
```

Output:
```html
<div style="color:red; font-size:120%;">
This text is big and red.
</div>

<span class="highlight" style="font-weight:bold;"> inline content </span>
```

#### Anonymous Div (no tag name)

```
::[padding:10px; background:#eee;]
Content in a styled div.
::
```

Output:
```html
<div style="padding:10px; background:#eee;">
Content in a styled div.
</div>
```

#### Classes, IDs, and Inline Attributes

```
::(.classA .classB #myId)[margin:10px;]{data-role="main"}
Content
::
```

Output:
```html
<div class="classA classB" id="myId" style="margin:10px;" data-role="main">
Content
</div>
```

Classes and ID may also be chained without spaces: `::(.classA.classB#myId)`
gives the same attributes (since 2.5.1).

#### Self-Closing (inline)

End the content with `::` on the same line:

```
div::[color:blue;] short text ::
```

Output:
```html
<div style="color:blue;"> short text </div>
```

#### Closing Tags

A bare `::` closes the last opened tag. `::name[-]` and `::[-]` were removed
in 3.0 and raise `LHTMLParseError`. On a named tag, `[-]` is a style
(`span::[-]` is `<span style="-">`, as in LHTML 2), with a warning, since it
was most likely meant as a closing tag.

### Links

The URL of `link::`, `img::`, `video::` and `videoplay::` is never modified (`__`, `**`, `$` are kept), but for a final `**` or `__` that closes a bold or an italic opened before it on its line: `**img::a.png**` is an image in bold. Parentheses that are part of the URL are kept (`Mercury_(planet)`, `fig(1).png`), while a group starting with `.` or `#` is a class/id group. The URL may contain Jinja expressions (`img::{{ base }}/photo.jpg`, `link::{{ url_for('page') }}[Home]`), which are kept unchanged.

```
link::https://example.com[Click here]
link::page.html(.nav)[Back to home]
```

Output:
```html
<a href="https://example.com">Click here</a>
<a class="nav" href="page.html">Back to home</a>
```


### Images

```
img::photo.jpg[width:400px;]
```

Output:
```html
<img style="width:400px;" src="photo.jpg" alt="photo.jpg">
```


### Videos

```
video::assets/clip.mp4[width:600px;]
videoplay::assets/clip.mp4[width:600px;]
```

`videoplay` adds `autoplay loop muted playsinline` attributes (`playsinline`: on an iPhone, the video plays in the page instead of full screen). A poster is an attribute: `video::clip.mp4{poster="clip.jpg"}`. LHTML probes no file: the sources of a video are the one written, unless the caller passes a `media` resolver to `lhtml.run()`, which returns the sources to offer (transcoded variants, for instance):

```python
def media(src):
    return [(f'variants/{src}.webm', 'video/webm'), (src, 'video/mp4')]

html = lhtml.run(text, media=media)
```

An empty list keeps the source as written.


### Code Blocks

````
code::[python]
def hello():
    print("Hello, world!")
code::[-]
````

Output (Pygments HTML inside `<div class="code">`):
```html
<div class="code"><pre><span></span><span class="k">def</span><span class="w"> </span><span class="nf">hello</span><span class="p">():</span>
...
</pre></div>
```

Syntax highlighting is powered by Pygments: any language supported by Pygments can be used, case-insensitively. An empty language (`code::[]`) renders plain text; an unknown language renders plain text with a warning. The built-in `c++` language is C++ with the types of the [CGP library](https://github.com/drohmer/cgp) highlighted; other languages can be added (see [Custom Code Lexers](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md#custom-code-lexers)).

The colors come from a Pygments stylesheet, which you must include in your page. Generate one for the `.code` class (any [Pygments style](https://pygments.org/styles/) can replace `default`):

```bash
pygmentize -S default -f html -a .code > code.css
```


### Spacer

```
::nl
```

Output:
```html
<div style="height:1em;"></div>
```


### Verbatim

`verbatim::[]` was removed in 3.0 and raises `LHTMLParseError`. A code block
(`code::[text]` ... `code::[-]`) shows text as it is; raw HTML is written
directly. A `::#` or `verbatim::[]` inside an attribute group or inline code
is text.


### Line breaks

By default, line breaks of the source have no visual effect (as in HTML). With the option `-b` / `--line-breaks` (or `lhtml.run(text, line_breaks=True)`), each line break of the text is rendered with `<br>`, blank lines included:

```
Line 1            Line 1<br>
Line 2     =>     Line 2<br>
                  <br>
Other paragraph   Other paragraph
```

Images and videos are inline: images written one per line are stacked (write them on the same line to keep them side by side). Lines that start or end with a block element (headings, lists, `div::`, block-level HTML tags such as `<div>`, `<p>`, `<li>`, code blocks, `<script>`, display math, ...) are structure: they never get a `<br>` and blank lines next to them are ignored. The content of code blocks, scripts, comments and math is never modified, nor are the line breaks a tag writes in its own HTML: a style written on two lines (`span::[color:red;\nfont-size:90%]`), a link label on two lines (`link::`; raw HTML `<a>` is text), the lines of a `video::`.


### Comments

`::#` comments were removed in 3.0 and raise `LHTMLParseError`: write an HTML
comment `<!-- ... -->` (kept in the page) or, through Jinja, `{# ... #}`
(removed). `link::#intro[...]` (a link to an anchor) was never a comment.


### File Inclusion

`include::` was removed in 3.0: LHTML reads no file. Include before calling
LHTML, with Jinja (`{% include "header.html" %}`) for instance. An `include::`
where LHTML 2 would have expanded one, in the text or in a code block, raises
`LHTMLParseError` naming the file, rather than being left as text.


### Macros (custom tags from a configuration)

A macro is a named `::` tag declared in YAML (or a dict): a shortcut for an
HTML element with default classes and attributes. The styling stays
in CSS, so a deck or a site changes its look in one place.

```yaml
# macros.yaml (the definitions may also be at the top level)
macros:
  small:  {class: small}
  credit: {tag: span, class: credit}
  aside:  {class: aside}
  box:    {class: box}
  gap:    {class: gap, empty: true, variant: [s, m, l], default: m}
  demo:   {tag: iframe, class: demo, empty: true, url: src, attrs: 'frameborder="0"'}
```

```
aside::[top:400px;]
img::assets/figure.png[width:450px;]
::

box::(.good) **Correct** ::
gap::l
credit:: Image: Wikimedia Commons ::
demo::assets/demo/index.html
```

Output:
```html
<div class="aside" style="top:400px;">
<img style="width:450px;" src="assets/figure.png" alt="assets/figure.png">
</div>

<div class="box good"> <strong>Correct</strong> </div>
<div class="gap gap-l"></div>
<span class="credit"> Image: Wikimedia Commons </span>
<iframe class="demo" src="assets/demo/index.html" frameborder="0"></iframe>
```

| Field | Description |
|-------|-------------|
| `tag` | HTML element (default `div`) |
| `class` | Default classes (space separated) |
| `attrs` | Default HTML attributes |
| `empty` | No content: the element is closed at once (`gap::`, `demo::url`) |
| `url` | The text after `::` is the value of this attribute (`src`, `data-src`, ...) |
| `variant` | The list of the variants: the text after `::` selects one, added as the class `<first class>-<variant>` (an unknown one gives a warning) |
| `default` | Variant used when none is given (one of the variants) |
| `doc` | Description, ignored by LHTML (for documentation tools; `lhtml.describe_macro(name, spec)` gives what a definition renders) |

The classes written in the source come after those of the macro (its
`class`, then the classes of its `attrs`), and its style after a style of
the macro's `attrs`: the page wins the cascade. An id written `(#id)` or
`{id=...}` replaces the macro's. Any other attribute is given once, by the last of:
the `attrs` of the macro, its `url` (`demo::page.html`), the source
(`box::{title="x"}`); for `img::` and `link::`, their defaults (`src`,
`alt`, `href`) come first. An attribute the source writes twice in one
`{...}` is kept as written. The
other attributes are kept as written, spaces in their values included; a
`url` macro written without its URL (`demo::`) keeps the one of its
`attrs`. A quoted string holds its brackets: in `{...}`, a value quoted
after its `=` (`{title="a } b"}`, over several lines but not across a
blank line); in `[...]`, a CSS string (`[content:"]"]`). A tag whose groups
are left as text because of a closing bracket without its opening one is
warned. The `tag` of a macro is an HTML
element, rendered as it is - never through an LHTML tag (`tag: video` gives
`<video>`, not `video::`; `tag: img` with `url: src` gives `<img src>`), nor
through another macro. A macro is closed by `::`. Macros are
not active inside inline code (`` `box::` `` stays text), and a macro cannot
replace a built-in tag (`div`, `img`, ...). The URL of a `url` macro is kept
as written, as the one of `img::` (`demo::my__demo__.html`).

A variant may be closed at once like any element: `gap::l::`.

Declare them with `-m` / `--macros` (repeatable, later files win), or with
`lhtml.run(text, macros=...)`, a mapping of definitions;
`lhtml.load_macros(...)` reads them from a YAML file, or merges a list of
files and mappings (later ones replacing a macro of the same name;
`name: null` removes it). A
file holds the definitions at its top level or under its only key `macros`
(`macros` is thus not a macro name). An HTML void element
(`tag: hr`, `br`, ...) is always empty. Invalid definitions (unknown field,
wrong type) raise `LHTMLMacroError`.

```bash
lhtml -m macros.yaml slide.l.html
```


### Input

LHTML reads no front matter (3.0): `---` at the top of a document is text,
and the options come from the caller. Input text is normalized first: a
leading BOM is removed and CRLF line endings become LF.

The options are named arguments of `lhtml.run()` (see the
[Python API reference](#python-api-reference)).


## Using LHTML with Jinja2

LHTML leaves Jinja2 untouched, so a template can be written in LHTML: convert it to HTML first, then render it with Jinja2 (`pip install jinja2`).

`blog.l.html`:
```
= {{ page.title }}

{% for post in posts %}
div::(.post)
== link::{{ post.url }}[{{ post.title }}]
{{ post.summary }} **Read more**
::
{% endfor %}
```

```python
import jinja2
import lhtml

with open('blog.l.html', encoding='utf-8') as f:
    template = jinja2.Template(lhtml.run(f.read()))

html = template.render(page={'title': 'Blog'},
                       posts=[{'url': 'first.html', 'title': 'First post', 'summary': 'Hello.'}])
```

`lhtml.run()` produces the Jinja2 template:
```html
<h1>{{ page.title }}</h1>


{% for post in posts %}
<div class="post">
<h2><a href="{{ post.url }}">{{ post.title }}</a></h2>

{{ post.summary }} <strong>Read more</strong>
</div>
{% endfor %}
```

Jinja2 expressions can also be used in URLs (`img::{{ base }}/photo.jpg`) and in tag groups (`div::[color:{{ color }};]`).


## Python API Reference

```python
lhtml.run(text, *, macros=None, tags=None, line_breaks=False, media=None)  # -> HTML
lhtml.wrap(html, *, title='Webpage', css=(), js=())    # -> an HTML5 document
lhtml.load_macros(source)       # definitions from a YAML file, a mapping, or a list of them
```

| Argument | Type | Description |
|----------|------|-------------|
| `macros` | mapping | The definitions of the macros (see [Macros](#macros-custom-tags-from-a-configuration)); `lhtml.load_macros` reads files |
| `tags` | mapping | Tags written in Python, `{name: lhtml.Tag}` ([docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md)) |
| `line_breaks` | boolean | Render source line breaks as `<br>` |
| `media` | callable | `media(src) -> [(url, mime type)]`, the sources of a video |
| `title`, `css`, `js` | of `wrap` | The title, the stylesheets and the scripts (a name or a list) |

An argument spelled otherwise is a `TypeError`. LHTML reads no file:
`lhtml.load_macros` is the caller reading its macro files.

The problems of a text are `LHTMLWarning` warnings, each with its `line`
and `column`. A caller that collects them parses and renders itself:

```python
document = lhtml.parse(text, macros=macros, warn=False)   # warn=False: kept, not warned
html = lhtml.render(document, line_breaks=True)
for problem in document.problems:                         # in source order
    print(problem.line, problem.column, problem)
```

Each parse keeps its own problems, in threads too (no global state is
changed). An `LHTMLError` stops the parse: its `line`, `column`, `path`
(a macros file) say where, and its `problems` holds those found before it.
`lhtml.highlight(code, language)` gives the HTML of a code block, as
`code::[language]` renders it.

### Stability

The API is what `lhtml` exports (`lhtml.__all__`): `run`, `parse`,
`render`, `wrap`, `highlight`, `Tag`, `TAGS`, `Written`, the nodes,
`Attributes`, `LEXERS`, `load_macros`, `describe_macro`,
`registry_with_macros`, the errors, and the command `lhtml`. It changes
only with a major version (4.0), as the HTML LHTML writes for a source. The
modules inside the package (`lhtml.patterns`, `lhtml.process`,
`lhtml.tree`...) are its implementation and may change in any release.


## Design Principles

- **HTML-first**: Raw HTML is never modified. Only LHTML syntax triggers conversions. In particular, the following are never transformed: HTML tags and their attributes, including tags spanning multiple lines (URLs containing `__`, quoted values containing `>`, ...), `<script>` and `<style>` blocks (CSS `::before`, ...), HTML comments, and math (`\(...\)`, `\[...\]`, so that `\(x**2\)` reaches MathJax/KaTeX intact; since 3.0 a `$` is text, as in a price). Text between HTML tags is still processed.
- **Attributes stay literal**: styles, classes/IDs and HTML attributes in LHTML tag groups and headings are preserved without inline formatting (`div::(.my__class__)` keeps `my__class__`). Link labels still support formatting.
- **Template-friendly**: Jinja2 expressions (`{{ ... }}`), statements (`{% ... %}`) and comments (`{# ... #}`) pass through unchanged (see [Using LHTML with Jinja2](#using-lhtml-with-jinja2)).
- **Island grammar**: LHTML syntax "islands" float in a sea of opaque content (HTML, Jinja2 templates, LaTeX, etc.) that passes through untouched.
- **Minimal**: A few symbols (`::`, `=`, `*`, `**`, `__`, `` ` ``) cover most needs. No complex configuration required.
- **Composable**: LHTML works seamlessly with Jinja2 templates, making it suitable for static site generators.


## License

MIT, see [LICENSE.md](https://github.com/drohmer/lhtml/blob/main/LICENSE.md).
