# LHTML — Lightweight HTML

[![Tests](https://github.com/drohmer/lhtml/actions/workflows/tests.yml/badge.svg?branch=feature/lhtml-v2)](https://github.com/drohmer/lhtml/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/lhtml-markup)](https://pypi.org/project/lhtml-markup/)

LHTML is a markup language that simplifies HTML authoring with embedded CSS styling. It is designed to be **HTML-first**: raw HTML passes through untouched, and only a few shorthand symbols (`::`, `*`, `=`, `**`, `__`) trigger conversions.

LHTML is used to build static websites and presentation slides, typically combined with Jinja2 templates.

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
lhtml input.l.html -w                 # Wrap in full HTML document
python -m lhtml input.l.html          # Alternative invocation
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
** Nested item A
** Nested item B
*** Deep nested
* Back to top level
```

Produces nested `<ul><li>` structures.


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


### Tag Elements (the `::` system)

The core of LHTML. The general syntax is:

```
tagName::(.classes #id)[cssStyle]{htmlAttributes} content ::
```

All bracket groups are optional. If `tagName` is omitted, defaults to `div`.

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

Syntax highlighting is powered by Pygments. Any language supported by Pygments can be used.


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


### Comments

```
Some text ::# This comment will be removed
```


### File Inclusion

```
include::header.html
include::components/nav.html
```

Included files are recursively processed (up to 20 levels).


### YAML Front Matter

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
| `directory_include` | list | Directories to search for includes |


## Plugin System

### Custom Tag Handlers

Register handlers for new `::` tag types:

```python
from lhtml.pipeline import tag_registry

def handle_alert(element, tag_to_close, current_directory):
    style = element.get('[]', '')
    text = element.get('text', '')
    return f'<div class="alert" style="{style}">{text}</div>', True

tag_registry.register('alert', handle_alert)
```

Then use in LHTML:
```
alert::[background:yellow; padding:10px;] Warning message ::
```

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
    'title': 'Webpage',        # Document title
    'css': [],                 # CSS files (string or list)
    'js': [],                  # JS files (string or list)
    'directory_include': [],   # Search paths for include::
    'current_directory': '',   # Base directory for video codec detection
}
```


## Design Principles

- **HTML-first**: Raw HTML is never modified. Only LHTML syntax triggers conversions.
- **Island grammar**: LHTML syntax "islands" float in a sea of opaque content (HTML, Jinja2 templates, LaTeX, etc.) that passes through untouched.
- **Minimal**: A few symbols (`::`, `=`, `*`, `**`, `__`, `` ` ``) cover most needs. No complex configuration required.
- **Composable**: LHTML works seamlessly with Jinja2 templates, making it suitable for static site generators.


## Project Structure

```
src/lhtml/
  __init__.py          # Public API: run(), analyse_tag(), read_yaml()
  cli.py               # Command-line interface
  pipeline.py          # ProcessingPipeline, TagRegistry, LexerRegistry
  process.py           # Core transformation functions
  patterns.py          # Centralized regex patterns and utilities
  tag_parser.py        # Lark-based parser for :: bracket syntax
  tag_element.lark     # Lark grammar definition
  export_html.py       # HTML generation for tag elements
  listing.py           # List processing
  code.py              # Code syntax highlighting (Pygments)
  wrap_html.py         # HTML document wrapping
  ast_nodes.py         # AST node dataclasses
  errors.py            # Structured error types
```


## License

MIT
