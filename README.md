# LHTML — Lightweight HTML

[![Tests](https://github.com/drohmer/lhtml/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/drohmer/lhtml/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/lhtml-markup)](https://pypi.org/project/lhtml-markup/)

LHTML is a markup language that simplifies HTML authoring with embedded CSS styling. It is designed to be **HTML-first**: raw HTML passes through untouched, and only a few shorthand symbols (`::`, `*`, `=`, `**`, `__`) trigger conversions.

LHTML is used to build static websites and presentation slides, typically combined with Jinja2 templates.

See the [examples](examples/) and the [changelog](CHANGELOG.md).

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

Dependencies (`lark`, `pygments`, `pyyaml`) are installed automatically.


## Quick Start

### Command Line

```bash
lhtml input.l.html                    # Convert to stdout
lhtml input.l.html -o output.html     # Convert to file
lhtml input.l.html -w                 # Wrap in full HTML document (--wrapAuto)
lhtml input.l.html -b                 # Render source line breaks as <br> (--line-breaks)
lhtml a.l.html b.l.html               # Several files: a.html, b.html next to sources
lhtml a.l.html b.l.html -o build/     # Several files into a directory
python -m lhtml input.l.html          # Alternative invocation
```

Without `-o`, `page.l.html` is written to `page.html` next to its source.

- Files are read and written as UTF-8 (a BOM is accepted).
- Errors and warnings are reported on stderr with the file name. The remaining files are still processed, and the exit code is non-zero if any file failed.
- An input file is never overwritten: `lhtml page.html` (output `page.html`) is an error, as is an output that is another input of the batch, or a symbolic or hard link to one.
- Includes are looked up in the input file's directory first, then in the current directory.

With `-w`, the result is wrapped in a minimal HTML document using the `title`, `css` and `js` of the front matter:

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

html = lhtml.run(text, {
    'wrap-auto': True,
    'title': 'My Page',
    'css': ['style.css'],
    'js': ['script.js'],
})
```


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

Output (a nested list is placed in its own `<li>`):
```html
<ul>
<li>
First item
</li>
<li>
Second item
</li>
<li>
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

Each `*` adds one level (`***` is level 3). A list ends at the first line that is not an item.


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

Inside inline code, `<` and `>` are escaped (so `` `std::vector<float>` `` displays correctly), and `**`, `__`, `$`, `include::`, `code::` and `::#` are not interpreted. Existing entities such as `&lt;` are kept. Named tags such as `link::` remain active, but a bare `::` is C++ (`` `::glfwInit()` ``), not a closing tag.


### Tag Elements (the `::` system)

The core of LHTML. The general syntax is:

```
tagName::(.classes #id)[cssStyle]{htmlAttributes} content ::
```

All bracket groups are optional. If `tagName` is omitted, defaults to `div`.

Tag names start with a letter and may contain letters, digits, `_` and `-` (useful for custom tags). A tag is only recognized when it is not glued to a preceding word: `std::chrono::seconds`, `obj.link::x` or the Python slice `a[::2]` are left untouched.

A closing `::` may be directly followed by punctuation or HTML (`**span::[c] x ::**`, `important ::,`). In a run of colons, `::` markers are the pairs ending the run: `::::[...]` is a closing `::` followed by `::[...]`, and `x:::nl` is `x:` followed by `::nl`. A `::` between two HTML tags (as in pre-highlighted code `<span>::</span>`) is left untouched.

A tag that is opened but never closed, or a `::` without matching opening tag, produces an `LHTMLWarning` quoting the beginning of the tag. An unmatched `::` is kept as text in the output.

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

#### Self-Closing (inline)

End the content with `::` on the same line:

```
div::[color:blue;] short text ::
```

Output:
```html
<div style="color:blue;"> short text </div>
```

#### Explicit Closing Tags

A bare `::` closes the last opened tag. To make long or nested blocks easier to read, name the tag you close with `::name[-]` (`::[-]` closes the last one, like `::`):

```
div::[color:red;]
Red **text**
::div[-]
```

Output:
```html
<div style="color:red;">
Red <strong>text</strong>
</div>
```

If the name does not match the last opened tag, a `LHTMLWarning` is emitted and the last opened tag is closed.


### Links

The URL of `link::`, `img::`, `video::` and `videoplay::` is never modified (`__`, `**`, `$` are kept). Parentheses that are part of the URL are kept (`Mercury_(planet)`, `fig(1).png`), while a group starting with `.` or `#` is a class/id group. The URL may contain Jinja expressions (`img::{{ base }}/photo.jpg`, `link::{{ url_for('page') }}[Home]`), which are kept unchanged.

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

`videoplay` adds `autoplay loop muted` attributes. The parser automatically detects transcoded codec variants (`-vp9.webm`, `-h265.mp4`, `-h264.mp4`) and poster images (`-poster.jpg`).


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

Syntax highlighting is powered by Pygments: any language supported by Pygments can be used, case-insensitively. An empty language (`code::[]`) renders plain text; an unknown language renders plain text with a warning. The built-in `c++` language is C++ with the types of the [CGP library](https://github.com/drohmer/cgp) highlighted; other languages can be added (see [Custom Code Lexers](#custom-code-lexers)).

The colors come from a Pygments stylesheet, which you must include in your page. Generate one for the `.code` class (any [Pygments style](https://pygments.org/styles/) can replace `default`):

```bash
pygmentize -S default -f html -a .code > code.css
```

`include::file` directives inside a code block insert the file as raw code.


### Spacer

```
::nl
```

Output:
```html
<div style="height:1em;"></div>
```


### Verbatim (raw passthrough)

Content inside verbatim blocks is preserved exactly as-is, with no LHTML processing:

```
verbatim::[]
This = is not a title
**not bold** __not italic__
div::[not a tag]
verbatim::[-]
```


### Line breaks

By default, line breaks of the source have no visual effect (as in HTML). With the option `-b` / `--line-breaks` (or `line-breaks: true` in the YAML front matter, or `{'line-breaks': True}` in the `meta` passed to `lhtml.run()`), each line break of the text is rendered with `<br>`, blank lines included:

```
Line 1            Line 1<br>
Line 2     =>     Line 2<br>
                  <br>
Other paragraph   Other paragraph
```

Images and videos are inline: images written one per line are stacked (write them on the same line to keep them side by side). Lines that start or end with a block element (headings, lists, `div::`, block-level HTML tags such as `<div>`, `<p>`, `<li>`, code and verbatim blocks, `<script>`, display math, ...) are structure: they never get a `<br>` and blank lines next to them are ignored. The content of code blocks, verbatim blocks, scripts, comments and math is never modified.


### Comments

```
Some text ::# This comment will be removed
```

A comment starts a line or follows whitespace, so `link::#intro[...]` (link to an anchor) is not a comment.


### File Inclusion

```
include::header.html
include::components/nav.html
```

Included files are recursively processed (up to 20 levels); their own YAML front matter is ignored. An included file looks for its own includes first in its own directory, then in `directory_include`. A circular include raises `LHTMLIncludeLoopError`.


### YAML Front Matter

The front matter must be at the very beginning of the file (`---` separators elsewhere are kept as text). Input text is normalized first: a leading BOM is removed and CRLF line endings become LF.

```
---
title: "My Page"
css: ["style.css", "theme.css"]
js: "app.js"
wrap-auto: true
---

= Page content starts here
```

Supported metadata keys:

| Key | Type | Description |
|-----|------|-------------|
| `title` | string | Page title (used in HTML wrapper) |
| `css` | string or list | CSS files to include |
| `js` | string or list | JavaScript files to include |
| `wrap-auto` | boolean | Wrap output in full HTML document |
| `line-breaks` | boolean | Render source line breaks as `<br>` |
| `directory_include` | list | Directories to search for includes |


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


## Plugin System

### Custom Tag Handlers

Register handlers for new `::` tag types:

```python
from lhtml.pipeline import tag_registry

def handle_alert(element, tag_to_close, current_directory):
    """Open <div class="alert">; the following :: closes it."""
    style = element.get('[]', '')
    tag_to_close.append('div')
    return f'<div class="alert" style="{style}">', True

tag_registry.register('alert', handle_alert)
```

Then use in LHTML:
```
alert::[background:yellow; padding:10px;] Warning message ::
```

A handler receives the parsed element (`'[]'`, `'()'`, `'{}'`, `'text'`: the
word glued after the brackets) and returns `(html, is_real_tag)`. To wrap the
content that follows, push the HTML tag name on `tag_to_close`: the next `::`
(or `::name[-]`) closes it. Returning `is_real_tag=False` leaves the source
text unchanged.

### Custom Code Lexers

Register custom Pygments lexers for syntax highlighting:

```python
from lhtml.pipeline import lexer_registry
from pygments.lexers import PythonLexer

lexer_registry.register('mypython', PythonLexer)
```

### Custom Pipeline

Create an isolated pipeline with its own tag registry:

```python
from lhtml.pipeline import ProcessingPipeline, TagRegistry

registry = TagRegistry()
registry.register('note', my_note_handler)

pipeline = ProcessingPipeline(registry=registry)
html = pipeline.run(text, {'wrap-auto': True})
```


## Configuration Reference

All keys for the `meta` dict passed to `lhtml.run()`:

```python
{
    'wrap-auto': False,        # Wrap in HTML document
    'line-breaks': False,      # Render source line breaks as <br>
    'title': 'Webpage',        # Document title
    'css': [],                 # CSS files (string or list)
    'js': [],                  # JS files (string or list)
    'directory_include': [cwd],  # Search paths for include:: (default: current directory)
    'current_directory': '',   # Base directory for video codec detection
}
```


## Design Principles

- **HTML-first**: Raw HTML is never modified. Only LHTML syntax triggers conversions. In particular, the following are never transformed (not even by `include::` or `::#`): HTML tags and their attributes, including tags spanning multiple lines (URLs containing `__`, quoted values containing `>`, ...), `<script>` and `<style>` blocks (CSS `::before`, ...), HTML comments, and math (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`, so that `$x**2$` reaches MathJax/KaTeX intact). Text between HTML tags is still processed.
- **Attributes stay literal**: styles, classes/IDs and HTML attributes in LHTML tag groups and headings are preserved without inline formatting (`div::(.my__class__)` keeps `my__class__`). Link labels still support formatting.
- **Template-friendly**: Jinja2 expressions (`{{ ... }}`), statements (`{% ... %}`) and comments (`{# ... #}`) pass through unchanged (see [Using LHTML with Jinja2](#using-lhtml-with-jinja2)).
- **Island grammar**: LHTML syntax "islands" float in a sea of opaque content (HTML, Jinja2 templates, LaTeX, etc.) that passes through untouched.
- **Minimal**: A few symbols (`::`, `=`, `*`, `**`, `__`, `` ` ``) cover most needs. No complex configuration required.
- **Composable**: LHTML works seamlessly with Jinja2 templates, making it suitable for static site generators.


## Project Structure

```
src/lhtml/
  __init__.py          # Public API: run(), analyse_tag(), read_yaml()
  __main__.py          # python -m lhtml
  cli.py               # Command-line interface
  pipeline.py          # ProcessingPipeline, TagRegistry, LexerRegistry
  process.py           # Core transformation functions
  patterns.py          # Centralized regex patterns and utilities
  tag_parser.py        # Lark-based parser for :: bracket syntax
  tag_element.lark     # Lark grammar definition
  element_extract.py   # extract_bracket_elements() (entry point of the tag parser)
  export_html.py       # HTML generation for tag elements
  listing.py           # List processing
  code.py              # Code syntax highlighting (Pygments)
  wrap_html.py         # HTML document wrapping
  errors.py            # Structured error types
  insert_in_text.py    # Store/restore helpers kept for backward compatibility
test/                  # pytest suite and .l.html / -out.html reference pairs
examples/              # Example sources (see examples/README.md)
```

Run the tests with `pytest` (after `pip install -e ".[dev]"`).


## License

MIT, see [LICENSE.md](LICENSE.md).
