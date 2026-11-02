# LHTML — Lightweight HTML

[![Tests](https://github.com/drohmer/lhtml/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/drohmer/lhtml/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/lhtml-markup)](https://pypi.org/project/lhtml-markup/)

**Documentation, with a tutorial and live examples: https://scholartools.fr/lhtml/** (English, français)

LHTML is a markup language that simplifies HTML authoring with embedded CSS styling. It is designed to be **HTML-first**: raw HTML passes through untouched, and only a few shorthand symbols (`::`, `*`, `=`, `**`, `__`) trigger conversions.

Requires Python 3.10 or newer. Install `lhtml-markup`; run `lhtml`; `import lhtml`.

To build presentations or a complete website, with themes and navigation, use
[lhtml-site](https://github.com/drohmer/lhtml-site), the generator built on
LHTML: its guide explains how to install it and start (it installs LHTML on
its own).

See the [examples](https://github.com/drohmer/lhtml/tree/main/examples/) and the [changelog](https://github.com/drohmer/lhtml/blob/main/CHANGELOG.md).


## Installation

The package `lhtml-markup` is on PyPI, the catalog of Python packages; pipx
and pip are two tools that install it from there (with its dependencies,
`pygments` and `pyyaml`). **pipx** suits the
command `lhtml`, **pip** the library used in a Python project. Pick the path
you need: each ends with a page you can open.

### The command, and a first page

Install [pipx](https://pipx.pypa.io/stable/installation/) if you do not have
it, then LHTML:

```bash
pipx install lhtml-markup
lhtml --version
```

**1.** Create a file `page.l.html`:

```
= My first page

Some **bold** and __italic__ text, and a link::https://example.org[link].

div::[color:gray;]
A gray block.
::
```

**2.** Convert it to a complete HTML page:

```bash
lhtml page.l.html --title "My first page" -o page.html
```

**3.** Open `page.html` in a browser (`open page.html` on macOS, `xdg-open
page.html` on Linux, `start page.html` on Windows).

Then:

- **A stylesheet**: `--css style.css` links it (as written, relative to the
  page); it may be repeated. A code block needs one for its colors, see
  [Code blocks](#code-blocks).
- **Only the content**: without `--title` (or `-w`), `lhtml` writes the HTML
  of the content alone, without `<html>`, `<head>` and `<body>`: the form to
  put in a template (see [Using LHTML with Jinja2](#using-lhtml-with-jinja2)).
- **The names**: a source is usually named `page.l.html`, and `lhtml` writes
  `page.html` (any name works: `notes.txt` gives `notes.html`). In a site
  built with lhtml-site, a page is instead a Jinja2 template written in
  LHTML, `page.html.j2`, rendered by the generator, not by `lhtml` (which
  would write `page.html.html`, its Jinja2 left as it is).
- **Later**: `pipx upgrade lhtml-markup` updates it. `pipx run --spec
  lhtml-markup lhtml page.l.html` runs it once without installing it.

### The library, from Python

In a virtual environment of your project. On macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install lhtml-markup
```

On Windows, in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install lhtml-markup
```

(Homebrew and recent system Pythons refuse a `pip install` outside a virtual
environment, with `externally-managed-environment`.) Then, in a file
`hello.py`:

```python
import lhtml

html = lhtml.wrap(lhtml.run("= Hello\n\nSome **bold** text.\n"), title="Hello")
with open("page.html", "w", encoding="utf-8") as f:
    f.write(html)
```

`python hello.py` writes `page.html`, to open in a browser. `lhtml.run`
converts a text, `lhtml.wrap` makes it a complete page (`css=[...]`,
`js=[...]`: its stylesheets and scripts): that is the whole API of a page, see
the [Python API reference](#python-api-reference). The environment has the
command `lhtml` too, and `python -m lhtml` is the same command.

### When something goes wrong

- **`pipx: command not found`**: install pipx first, see
  [its installation](https://pipx.pypa.io/stable/installation/).
- **`lhtml: command not found` after `pipx install`**: run `pipx ensurepath`,
  then open a new terminal.
- **`import lhtml` fails after `pipx install`**: pipx installs the command
  in an environment of its own, which your Python does not see. Follow
  [The library, from Python](#the-library-from-python), in the environment
  of your project.


## Syntax at a glance

Each line of LHTML on the left, what it gives on the right:

| LHTML | gives | Details |
|-------|-------|---------|
| `= Title` | `<h1>Title</h1>` | [Headings](#headings) |
| `== Section` | `<h2>Section</h2>` (and so on to `======`; more `=` stay text, with a warning) | [Headings](#headings) |
| `* item` | a list (`** item` for a nested one) | [Lists](#lists) |
| `**bold** and __italic__` | `<strong>bold</strong> and <em>italic</em>` | [Inline formatting](#inline-formatting) |
| `` `code` `` | inline code, never read as LHTML | [Inline formatting](#inline-formatting) |
| `div::[color:gray;]`, lines, then `::` | `<div style="color:gray;">`, the lines, `</div>` | [Blocks and styles](#blocks-and-styles) |
| `div::(.note #intro)` (also after `=`, `link::`, `img::`...) | `<div class="note" id="intro">` | [Classes and ids](#classes-and-ids) |
| `link::https://example.org[text]` | `<a href="https://example.org">text</a>` | [Links](#links) |
| `img::photo.jpg[width:300px;]` | `<img style="width:300px;" src="photo.jpg" alt="photo.jpg">` | [Images](#images) |
| `code::[python]`, lines, then `code::[-]` | the lines as a highlighted Python code block | [Code blocks](#code-blocks) |
| `<b>raw HTML</b>` | kept as it is; so are `\(math\)` and `{{ jinja }}` | [Design principles](#design-principles) |
| `note:: text ::`, with `-m macros.yaml` | `<div class="note"> text </div>`: a tag of your own, declared in YAML | [Macros](#macros) |

Everything else is HTML, written as it is: a paragraph `<p>`, a numbered
list `<ol>`, a table, a quote. In particular a blank line does not make a
paragraph, as in HTML: write `<p>`, or render the line breaks of the source
with `-b` (see [Line breaks](#line-breaks)).

The [Syntax reference](#syntax-reference) below details each construct;
[docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md)
is for callers that extend LHTML in Python.


## Command line

```bash
lhtml page.l.html                         # to stdout
lhtml page.l.html -o page.html            # to a file
lhtml page.l.html --title Notes --css style.css -o page.html   # a complete page
lhtml a.l.html b.l.html -o build/         # several files, into a directory
cat page.l.html | lhtml -                 # the standard input
```

| Option | Effect | Default |
|--------|--------|---------|
| `input ...` | The files to convert; `-` for the standard input (alone) | |
| `-o`, `--output OUTPUT` | The output file (one input), or directory (several inputs, or a trailing `/`) | stdout for one input; several are written next to their sources (`a.l.html` to `a.html`) |
| `-w`, `--wrap` | Wrap the HTML in a document (`<!DOCTYPE html>`, `<head>`, `<body>`), as `lhtml.wrap` (see the [Python API reference](#python-api-reference)) | the content alone, to put in a template |
| `--title TITLE` | The title of the document (implies `-w`) | `Webpage` |
| `--css URL` | A stylesheet of the document, linked as written (implies `-w`); may be repeated | none |
| `--js URL` | A script of the document (implies `-w`); may be repeated | none |
| `-b`, `--line-breaks` | Render the line breaks of the source as `<br>` (see [Line breaks](#line-breaks)) | as in HTML: no effect |
| `-m`, `--macros FILE` | A YAML file of macros, custom `::` tags (see [Macros](#macros)); may be repeated, later files win | none |
| `-v`, `--verbose` | Name each file written | |
| `-q`, `--quiet` | No summary (`2 converted · 1 warning`) | a summary when files are written |
| `-V`, `--version` | Show the version and exit (from Python: `lhtml.__version__`) | |
| `-h`, `--help` | Show the help, its exit statuses and examples, and exit | |

Where files are written, the messages and the exit status:
[Command line details](#command-line-details).


## Syntax reference

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


### Inline formatting

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


### Blocks and styles

The `::` system, the core of LHTML. The general syntax is:

```
tagName::(.classes #id)[cssStyle]{htmlAttributes} content ::
```

All bracket groups are optional. If `tagName` is omitted, defaults to `div`. A bare `::` closes the last opened tag.

#### Div and span with styles

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

#### Anonymous div (no tag name)

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

#### Closed on the same line

End the content with `::` on the same line:

```
div::[color:blue;] short text ::
```

Output:
```html
<div style="color:blue;"> short text </div>
```

#### Precise rules of the tags

*To skip on a first reading.*

- **Names**: a tag name starts with a letter and may contain letters,
  digits, `_` and `-` (useful for custom tags).
- **Not glued**: a tag is only recognized when it is not glued to a
  preceding word: `std::chrono::seconds`, `obj.link::x` or the Python slice
  `a[::2]` are left untouched.
- **The closing `::`** may be directly followed by punctuation or HTML
  (`**span::[c] x ::**`, `important ::,`). A marker is exactly two colons:
  a run of three or more (`:::`, `::::`) is text. A `::` between two HTML
  tags (as in pre-highlighted code `<span>::</span>`) is left untouched.
- **Quoted strings** hold their brackets: in `{...}`, a value quoted after
  its `=` (`{title="a } b"}`, over several lines but not across a blank
  line); in `[...]`, a CSS string (`[content:"]"]`). A tag whose groups are
  left as text because of a closing bracket without its opening one is
  warned.
- **Defaults of `img::` and `link::`**: their `src`, `alt` and `href` come
  first, and an attribute written in the source replaces them
  (`img::a.png{alt="x" src="b.png"}` is `<img alt="x" src="b.png">`).
- **Unclosed or unmatched**: a tag that is opened but never closed, or a
  `::` that closes nothing, produces a warning quoting the beginning of the tag
  (printed by the command; from Python, an `LHTMLWarning`, see the
  [Python API reference](#python-api-reference)). A tag never closed is not
  closed in the output either: `div::` gives an opening `<div>` without its
  `</div>`. An unmatched `::` is kept as text in the output.
- **Nesting**: elements nest inside headings, list items, bold and italic.
  One opened there and not closed there is closed at its end, with a
  warning.
- **Which `::` closes**: a `::` closes the last open element only when both
  are in the same heading, item, bold or italic (or both outside). In
  `div:: a **x :: y** b ::` the `::` inside the bold closes nothing (a
  warning, it stays as text) and the last one closes the div.
- **Where**: every warning or error, of a tag or not, has the `line` and
  `column` where it is in the text given to `lhtml.run` (`None` when not
  known). The command line prints each problem as
  `file:line:column: level: message`.


### Classes and ids

The group `(...)` gives classes (`.name`) and an id (`#name`) to an element:
a block or a span, a heading (`=(.highlight #intro) Title`), a link
(`link::page.html(.nav)[Home]`), an image, a macro. With a style `[...]` and
other attributes `{...}`:

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

Classes and the id may also be chained without spaces: `::(.classA.classB#myId)`
gives the same attributes (since 2.5.1).


### Links

```
link::https://example.com[Click here]
link::page.html(.nav)[Back to home]
```

Output:
```html
<a href="https://example.com">Click here</a>
<a class="nav" href="page.html">Back to home</a>
```

A link without a label shows its URL (`link::https://example.org` is
`<a href="https://example.org">https://example.org</a>`), as an image
without `alt` gets its source. An image as a link is
`link::page.html[img::thumb.png]`
(`<a href="page.html"><img src="thumb.png" alt="thumb.png"></a>`).

#### Precise rules of the URLs and labels

*To skip on a first reading.*

- **The URL** of `link::`, `img::`, `video::` and `videoplay::` is never
  modified (`__`, `**`, `$` are kept), but for a final `**` or `__` that
  closes a bold or an italic opened before it on its line: `**img::a.png**`
  is an image in bold.
- **Parentheses** that are part of the URL are kept (`Mercury_(planet)`,
  `fig(1).png`), while a group starting with `.` or `#` is a class/id
  group.
- **Jinja** expressions in the URL (`img::{{ base }}/photo.jpg`,
  `link::{{ url_for('page') }}[Home]`) are kept unchanged.
- **A label** holds text, bold, italic, inline code, and the elements that
  hold nothing: an image, a `video::`, an empty macro or `span::word::`. An
  element that would hold what follows (`div::`) or another link stays text
  in a label, with a warning.
- **Links across**: a `link::` whose label would cross the end of a
  heading, an item or a bold (`**x link::u[b** c]`) is left as text, with a
  warning.


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

`videoplay` adds `autoplay loop muted playsinline` attributes (`playsinline`: on an iPhone, the video plays in the page instead of full screen). A poster is an attribute: `video::clip.mp4{poster="clip.jpg"}`. The output is a `<video>` with a `<source>`, and a text shown by a browser that cannot play it:

```html
<video style="width:600px;">
	<source src="assets/clip.mp4" type="video/mp4">
	 Cannot play video assets/clip.mp4
</video>
```

LHTML probes no file: the sources of a video are the one written, unless the caller passes a `media` resolver to `lhtml.run()`, which returns the sources to offer (transcoded variants, for instance):

```python
def media(src):
    return [(f'variants/{src}.webm', 'video/webm'), (src, 'video/mp4')]

html = lhtml.run(text, media=media)
```

An empty list keeps the source as written.


### Code blocks

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

A code block is the one construct closed by `code::[-]` rather than `::`:
its lines are never read as LHTML, so a `::` in the code (`std::vector`)
cannot close it. (The `[-]` closers of the other tags were removed in 3.0,
see [Removed in 3.0](#removed-in-30).)

Syntax highlighting is powered by Pygments:

- any language supported by Pygments can be used, case-insensitively;
- an empty language (`code::[]`) renders plain text, an unknown language
  plain text with a warning;
- the built-in `c++` language is C++ with the types of the
  [CGP library](https://github.com/drohmer/cgp) highlighted;
- other languages can be added (see [Custom code lexers](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md#custom-code-lexers)).

The colors come from a Pygments stylesheet, which you must include in your page. Generate one for the `.code` class (any [Pygments style](https://pygments.org/styles/) can replace `default`):

```bash
pipx run --spec pygments pygmentize -S default -f html -a .code > code.css
```

Where Pygments is installed (a virtual environment with LHTML), run `pygmentize -S default -f html -a .code > code.css` directly; a pipx installation provides `lhtml` only.

Then link it to the page: `lhtml page.l.html --title "My page" --css code.css -o page.html`.


### Spacer

```
::nl
```

Output:
```html
<div style="height:1em;"></div>
```

For spaces of several heights, rather than `::[height:25px;]::` written by
hand on each page, a `gap` macro keeps them in the stylesheet, one place to
change them (see [Macros](#macros) below).


### Line breaks

By default, line breaks of the source have no visual effect (as in HTML). With the option `-b` / `--line-breaks` (or `lhtml.run(text, line_breaks=True)`), each line break of the text is rendered with `<br>`, blank lines included:

```
Line 1            Line 1<br>
Line 2     =>     Line 2<br>
                  <br>
Other paragraph   Other paragraph
```

With `-b`:

- **Images and videos are inline**: images written one per line are stacked
  (write them on the same line to keep them side by side).
- **Structure gets no `<br>`**: lines that start or end with a block element
  (headings, lists, `div::`, block-level HTML tags such as `<div>`, `<p>`,
  `<li>`, code blocks, `<script>`, display math, ...) never get a `<br>`,
  nor does the line just before one, and blank lines next to them are
  ignored.
- **Never modified**: the content of code blocks, scripts, comments and
  math, and the line breaks a tag writes in its own HTML: a style written on
  two lines (`span::[color:red;\nfont-size:90%]`), a link label on two lines
  (`link::`; raw HTML `<a>` is text), the lines of a `video::`.


### Macros

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

`gap` gives one class per height, set in the stylesheet: `gap::` is a medium
space, `gap::l` a large one.

```css
.gap-s { height: 0.5em; }  .gap-m { height: 1em; }  .gap-l { height: 2em; }
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

A macro is closed by `::`, and a variant may be closed at once like any
element: `gap::l::`.

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

#### Precise rules of the macros

*To skip on a first reading.*

- **Classes and style**: the classes written in the source come after those
  of the macro (its `class`, then the classes of its `attrs`), and its style
  after a style of the macro's `attrs`: the page wins the cascade.
- **Id**: an id written `(#id)` or `{id=...}` replaces the macro's.
- **Other attributes**: each is given once, by the last of: the `attrs` of
  the macro, its `url` (`demo::page.html`), the source (`box::{title="x"}`)
  (for `img::` and `link::`, their defaults come first, as for any tag). An
  attribute the source writes twice in one `{...}` is kept as written.
  Values are kept as written, spaces included.
- **A `url` macro**: its URL is kept as written, as the one of `img::`
  (`demo::my__demo__.html`); written without its URL (`demo::`), it keeps
  the one of its `attrs`.
- **The `tag`** of a macro is an HTML element, rendered as it is - never
  through an LHTML tag (`tag: video` gives `<video>`, not `video::`;
  `tag: img` with `url: src` gives `<img src>`), nor through another macro.
- **Where they apply**: macros are not active inside inline code
  (`` `box::` `` stays text), and a macro cannot replace a built-in tag
  (`div`, `img`, ...).


### Input

LHTML reads no front matter (3.0): `---` at the top of a document is text,
and the options come from the caller. Input text is normalized first: a
leading BOM is removed and CRLF line endings become LF.

The options are named arguments of `lhtml.run()` (see the
[Python API reference](#python-api-reference)).


### Removed in 3.0

For a source written for LHTML 2 (all the details: [docs/migration.md](https://github.com/drohmer/lhtml/blob/main/docs/migration.md)).
Each of these raises `LHTMLParseError`, which names the replacement:

| LHTML 2 | LHTML 3 |
|---------|---------|
| `::name[-]`, `::[-]` (closing tags; `code::[-]` still closes a code block) | a bare `::` |
| `verbatim::[]` | a code block `code::[text]` ... `code::[-]`, or raw HTML |
| `::#` comments | an HTML comment `<!-- ... -->` (kept in the page), or with Jinja `{# ... #}` (removed) |
| `include::file` | include before calling LHTML, with Jinja for instance (`{% include "header.html" %}`): LHTML reads no file |

On a named tag, `[-]` is a style (`span::[-]` is `<span style="-">`, as in
LHTML 2), with a warning, since it was most likely meant as a closing tag. A
`::#` or `verbatim::[]` inside an attribute group or inline code is text, and
`link::#intro[...]` (a link to an anchor) was never a comment.


## Command line details

Without `-o`, one input is written to stdout, and several inputs are each
written next to their source (`page.l.html` to `page.html`). With `-o`, one
input is written to that file, several into that directory; two inputs that
would be written to the same file are refused before anything is written.

- stdout holds the HTML only, stderr every message: `lhtml page.l.html > page.html` writes a clean file.
- The destinations are checked before any file is written: an input missing, two inputs written to one file (or to names that differ by case only, or to two names of one file), an output that is an input (or a symbolic or hard link to one), an output under a file: an error each, and nothing is written.
- Then each file is converted and written; one that fails does not stop the others. Writing files ends with a summary (`2 converted · 1 warning`).
- Exit status: 0; 1 when a file is not converted or not written; 2 for a wrong use of the command (`lhtml --help` says so too).
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
A message reads `subject: problem; what to do (near 'source')`; a name close
to a known one is suggested (`code::[pyhton]: unknown language, shown as
plain text; did you mean 'python'?`), and one mistake gives one warning (an
old closer `span::[-]` does not also warn the element it was meant to
close).


## Using LHTML with Jinja2

LHTML leaves Jinja2 untouched, so a template can be written in LHTML: convert it to HTML first, then render it with Jinja2 (`pip install jinja2`, in the virtual environment where LHTML is installed).

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
print(html)
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


## Python API reference

```python
lhtml.run(text, *, macros=None, tags=None, line_breaks=False, media=None, lexers=None)  # -> HTML
lhtml.wrap(html, *, title='Webpage', css=(), js=())    # -> an HTML5 document
lhtml.load_macros(source)       # definitions from a YAML file, a mapping, or a list of them
```

| Argument | Type | Description |
|----------|------|-------------|
| `macros` | mapping | The definitions of the macros (see [Macros](#macros)); `lhtml.load_macros` reads files |
| `tags` | mapping | Tags written in Python, `{name: lhtml.Tag}` ([docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md)) |
| `line_breaks` | boolean | Render source line breaks as `<br>` |
| `media` | callable | `media(src) -> [(url, mime type)]`, the sources of a video |
| `lexers` | mapping | `{name: Pygments lexer class}`, languages of the code blocks of this call ([docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md#custom-code-lexers)) |
| `title`, `css`, `js` | of `wrap` | The title, the stylesheets and the scripts (a name or a list) |

`lhtml.wrap('<h1>Hello</h1>', title='My Page', css=['style.css'], js=['app.js'])` gives:

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

An argument spelled otherwise is a `TypeError`. LHTML reads no file:
`lhtml.load_macros` is the caller reading its macro files (Pygments may: a
code block in a language it does not know makes it look for its plugins,
once per name).

The problems of a text are `LHTMLWarning` warnings (Python's `warnings`),
each with its `line` and `column`; an `LHTMLError` stops the conversion. A
caller that collects the problems, or changes the document before its HTML
is written, calls `lhtml.parse` and `lhtml.render` itself: see
[Parse, render, and the problems](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md#parse-render-and-the-problems).
`lhtml.highlight(code, language)` gives the HTML of a code block, as
`code::[language]` renders it.

### Stability

The API is what `lhtml` exports (`lhtml.__all__`): `run`, `parse`,
`render`, `wrap`, `highlight`, `Tag`, `TAGS`, `Written`, the nodes,
`Attributes`, `LEXERS`, `load_macros`, `describe_macro`,
`registry_with_macros`, `zones`, `Zone`, `read_tags`, `read_tag`, `SourceTag`, `URL_TAGS`, the errors,
and the command `lhtml`. It changes
only with a major version (4.0), as the HTML LHTML writes for a source. The
modules inside the package (`lhtml.patterns`, `lhtml.process`,
`lhtml.tree`...) are its implementation and may change in any release.


## Design principles

- **HTML-first**: Raw HTML is never modified. Only LHTML syntax triggers
  conversions; text between HTML tags is still processed. Never transformed:
  - HTML tags and their attributes, including tags spanning multiple lines
    (URLs containing `__`, quoted values containing `>`, ...);
  - `<script>` and `<style>` blocks (CSS `::before`, ...) and HTML comments;
  - math, `\(...\)` and `\[...\]`, so that `\(x**2\)` reaches MathJax/KaTeX
    intact (since 3.0 a `$` is text, as in a price).
- **Attributes stay literal**: styles, classes/IDs and HTML attributes in LHTML tag groups and headings are preserved without inline formatting (`div::(.my__class__)` keeps `my__class__`). Link labels still support formatting, and the elements that hold nothing (`link::u[img::a.png]`).
- **Template-friendly**: Jinja2 expressions (`{{ ... }}`), statements (`{% ... %}`) and comments (`{# ... #}`) pass through unchanged (see [Using LHTML with Jinja2](#using-lhtml-with-jinja2)).
- **Island grammar**: LHTML syntax "islands" float in a sea of opaque content (HTML, Jinja2 templates, LaTeX, etc.) that passes through untouched.
- **Minimal**: A few symbols (`::`, `=`, `*`, `**`, `__`, `` ` ``) cover most needs. No complex configuration required.
- **Composable**: LHTML works seamlessly with Jinja2 templates, making it suitable for static site generators.


## Editor support

[editors/vscode](https://github.com/drohmer/lhtml/tree/main/editors/vscode) is an extension for Visual Studio Code: highlighting of the LHTML
marks (and of the HTML, CSS, Jinja and code blocks around them), folding of the `::` blocks, and
snippets. It applies to `*.l.html` files and to the `index.html.j2` pages of an lhtml-site project;
[its README](https://github.com/drohmer/lhtml/blob/main/editors/vscode/README.md) tells how
to install it.


## Development

To work on LHTML, from its repository, in a virtual environment:

```bash
git clone https://github.com/drohmer/lhtml.git
cd lhtml
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"     # editable, with pytest
python -m pytest -q
```

The layout of the code, module by module, is in
[docs/advanced.md](https://github.com/drohmer/lhtml/blob/main/docs/advanced.md#layout-of-the-code).


## License

MIT, see [LICENSE.md](https://github.com/drohmer/lhtml/blob/main/LICENSE.md).
