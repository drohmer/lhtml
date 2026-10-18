# Changelog

All notable changes to LHTML (`lhtml-markup` on PyPI) are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.0.0] - Unreleased

In short: LHTML reads no file but its input; a text is parsed into a
document tree that `render` writes, and that a caller may read and change;
tags written in Python build nodes; the options are named arguments; the
problems carry their line and column, collected per parse
(`document.problems`); the syntax LHTML 2 deprecated is gone. From LHTML 2:
[docs/migration.md](docs/migration.md).

LHTML reads no file but its input and the macro files it is given: a
caller that reads its sources itself (a site generator) knows everything a
page depends on.

### Removed
- `include::`, in the text and inside code blocks. Where LHTML 2 would have
  expanded one, LHTML 3 raises `LHTMLParseError` naming the file, instead of
  leaving the directive as text. Include before calling LHTML (Jinja
  `{% include %}`, for instance). With it go `find_file`, `process_include`,
  `process_include_recursive`, `LHTMLFileNotFound`, `LHTMLIncludeLoopError`
  and the `directory_include` option.
- The poster convention: a `<name>-poster.jpg` next to a video is no longer
  looked for. Write it: `video::clip.mp4{poster="clip.jpg"}`.
- The detection of codec variants in `cache_video_codecs/` (and
  `CACHE_VIDEO_DIR`, `VIDEO_CODECS`): see `media` below.
- What no project of the corpus of the generator writes (1333 sources
  counted). Refused by name with `LHTMLParseError`, the replacement in the
  message: `::name[-]` and `::[-]` (close with `::`; on a named tag, `[-]`
  stays a style, with a warning), `::#` comments (HTML or Jinja comments),
  `verbatim::[]` (`code::[text]`, or raw HTML written directly). Now text: `$...$`,
  `$$...$$` and the one-character `$x$` rule (mathematics is `\(...\)` and
  `\[...\]`), runs of three colons or more (`:::nl`), tags inside inline
  code (`` `link::x` ``), the YAML front matter (options come from the
  caller, as named arguments).
- Macros: the `style` field, `variant: true` (a variant is a list), and the
  rendering through an LHTML tag (`tag: img`, `video`, `link` give the HTML
  element; `url` names the attribute).
- From the public API: `analyse_tag`, `read_yaml`, `process_yaml`, the
  `process_*` functions, `extract_bracket_elements`, `wrap_auto`,
  `insert_element_from_index` / `remove_element_to_index`
  (`insert_in_text.py`), and the dead constants of `patterns.py`.
- The dependency on `lark`: the tag element is parsed by one hand-written
  scanner (`tag_parser.extract_bracket_elements`, which also gives the span
  of each bracket group), checked identical on 17099 tags of real projects.
  `element_extract.py` and `tag_element.lark` go.
- `ProcessingPipeline`, `TagRegistry`, `LexerRegistry`, `tag_registry`,
  `lexer_registry` and `register_macros`: the built-in tags are a dict,
  `lhtml.TAGS`; custom ones are given to the run, `lhtml.run(text,
  tags={...})`; the lexers are a dict, `lhtml.LEXERS`;
  `registry_with_macros` returns a dict.
- `LHTMLTagStackError`, the positions of `LHTMLError` (`source_pos`,
  `source_line`) and `pos_to_line`: the messages quote the source instead.

- The `meta` dict of `run` and `render`, its `current_directory` and
  `wrap-auto`, and `context.meta`: the options are named arguments,
  `lhtml.run(text, macros=, tags=, line_breaks=, media=)` (an argument
  spelled otherwise is a `TypeError`); `lhtml.wrap(html, title=, css=,
  js=)` makes a document of the HTML; `macros` is a mapping, and the caller
  reads its files with `lhtml.load_macros(path or [paths])`. A tag written
  in Python keeps its own options in its closure.

The API is `run`, `parse`, `render`, `wrap`, `Tag`, `TAGS`, `Attributes`,
the nodes (`lhtml.nodes`), `LEXERS`, the macro functions and the errors.

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Messages for the mistakes authors make: `code::[python]` never closed
  (its lines were read as LHTML, silently), a `code::[-]` that closes no
  block (it was told it is a style), a name followed by a group that is no
  tag (`bxo::(.c)`), a `word::` written for a closing `word ::`. A name
  close to a known one is suggested (a language, a variant, a tag). One
  mistake gives one warning: an old closer `span::[-]` no longer also
  warns the element it was meant to close and the `::` after it. Every
  message reads `subject: problem; what to do (near 'source')`.
- The command reads the standard input (`lhtml -`, alone); `--title`,
  `--css` and `--js` give the document of `-w` its title, stylesheets and
  scripts (and imply it); `--help` says the exit status, with examples.
- `Attributes.add_class(*names)`. `load_macros` checks each definition, as
  `registry_with_macros` did (a wrong name or field was accepted until the
  tags were made); a file's error names its path.
- A link without a label shows its URL (`link::https://a.org`: it was an
  empty `<a>`).
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- `media`, an argument of `lhtml.run()`: a callable,
  `media(src) -> [(url, mime type)]`, listing the sources of a video. An
  empty list, or no resolver, keeps the source as written.
- The output of the command: stdout holds the HTML only, stderr every
  message (`lhtml/diagnostics.py`). A problem is
  `file:line:column: level: message`; in a terminal, the line of the source
  follows with the place underlined, for an error as for a warning (tabs, wide characters and long lines
  taken into account), the level colored (`NO_COLOR`, `FORCE_COLOR`,
  `TERM=dumb` respected). The destinations are computed, then checked, then
  written: an input missing, two inputs to one file (to names that differ
  by case only, or to two names of one file, a hard link), an output that
  is an input or lies under a file
  are each an error and nothing is written (a destination under a file was
  a traceback). Writing files ends with a summary (`2 converted · 1
  warning`; `-q` none, `-v` each file written); exit status 1 when a file
  is not converted or not written, 2 for a wrong use.
- `line` and `column` on `LHTMLWarning` and `LHTMLError`: where the problem
  is in the text given to `run` (1-based, `None` when not known, as for a
  macros file). A tag element carries its `line` and `column` to the
  `build` of its tag (`written.line`, `written.column`).
- `lhtml.parse(text)` gives the document tree (headings, lists, bold,
  italic, `::` elements, and code, inline code, mathematics, raw HTML as
  leaves), every node with its place (`span` in the text given, `line`,
  `column`); `lhtml.render(document)` its HTML. `lhtml.run` is both: the
  text passes are gone. The tree is walked and rendered without recursion,
  and a text of unclosed brackets is read in linear time (it was
  quadratic).

### Changed
- The attributes are read once and merged as `Attributes`, never written
  as text to be read again: `img::x.png(.a){class=""}` is `class="a"` (it
  was `class="a" class=""`), a variant of a macro is one class
  (`gap::a.b`: `gap-a.b`, it was cut at its dot), the `class` of a macro
  and the classes of its `attrs` are taken as written (`class: a.b` is
  `class="a.b"`, it was `a b`; `a#b` was a class and an id), an empty
  class or style of a macro's `attrs` is given, and a name keeps its
  Jinja as written (`data-{{ K }}` stayed `data-{{ k }}` once set). A class
  or a style written inside a Jinja block (`{% if x %}class="a"{% endif %}`)
  stays in it (it was joined to the others, unconditionally), and a
  statement glued to an unquoted value is part of it
  (`title=a{% if x %}b{% endif %}`). `describe_macro` gives the HTML the
  macro renders (one `class`).
- The diagnostics escape what their stream cannot encode, the whole line:
  a path or a message with an accent on an ASCII stream no longer drops
  it and those after it. A path on another drive (Windows) stays absolute.
- The document tree is authoritative: `render` writes the HTML from the
  fields of the nodes alone (`lhtml.nodes`, exported by `lhtml`), so a node
  changed changes the HTML. `Text.raw`, `Heading.markup_attributes`,
  `Element.groups`/`value`/`element`, the `index` of the zones and
  `Document.stores` are gone: no placeholder is left in the tree. An
  `Element` has `name` (the HTML element), `attributes` (an
  `lhtml.Attributes`, an ordered mapping that writes back what it read as
  written), `void`, `end_tag` and its children; the label of a link is its children
  (`Text`, `Strong`...), the word after a tag its content. A node is made
  as it reads, its place and children as keywords: `Text('a')`,
  `Element('div', {'class': 'c'}, children=[...])`, `Code(body, language)`.
  `Element.written` (an `lhtml.Written`: the tag, its groups and word as
  written) is information on the source, never read by `render`: how the
  source closed an element does not change its HTML (`end_tag` is False
  for an element still open at the end of the document). A tag is `lhtml.Tag(build, container, url)`:
  `build(written)` receives that `Written`, whose `attributes` are those
  its groups write, and returns its nodes (an `Element`, a `Raw` of HTML written as it is...),
  instead of a `render` returning HTML; the macros and the built-in tags
  are such builders (`video::` is a `Video` node, its sources asked of
  `media` at render). `render.py` and `nodes.py` leave `tree.py`.
  Changed on the way, by the same rules for every tag: `img::a.png::` is
  closed at once, `::` not in its URL (as a macro with `url:` did); a group
  across other nodes (`span::[**b**]`) is kept as written, where the HTML
  of the bold was written inside the attribute; inline code or a code
  block inside a group stays as written (its HTML was written inside the
  attribute); a `"` of a generated attribute (the id of a heading) is
  escaped; the text of a group of what is not an element gets its line
  breaks (`-b`) as any text, and the zones in it are zones.
- One reader for the attributes (`{...}`, the `attrs` of a macro, the
  defaults of a tag) and one rule when several give the same one: the tag,
  then the macro, then its `url`, then the page, the last one given; class
  and style add up (a class once). Replacing an attribute of a macro keeps
  the others as written (`title="a  b"` kept its two spaces only when
  nothing was replaced); a `url` macro whose `attrs` give `src` no longer
  writes two `src`, and `demo::` keeps the `src` of its `attrs`; a default
  of `videoplay::` written in the page is not doubled. A CSS string in
  `[...]` holds its brackets (`[content:"]"]`), a value quoted in `{...}`
  holds them across lines (not across a blank line), and a tag whose groups are left as
  text by a stray closing bracket is warned. A bracket left open in a
  paragraph before (`[0, 1)`) holds no string; a value without its closing
  quote is warned. A Jinja expression is part of a name or a value
  (`data-{{ k }}="v"`, `title={{ x }} alt="y"`: two attributes), and `{{%`
  is `{` then `{%`. An id is given once (`{id=...}` replaces `(#id)`, which
  replaces the macro's); the classes and the style of a macro's `attrs` come
  before those of the page.
- The handlers `(element, tag_to_close, context) -> (html, is_real_tag)`
  are gone: a tag is an `lhtml.Tag` (see the authoritative tree above);
  `lhtml.TAGS` (now read-only) and `registry_with_macros` give Tags. A tag
  given to `run` wins over the built-in tags and the macros, the anonymous
  `::` div included; its name is checked, and an exception of its `build`
  or `container` becomes an `LHTMLError` with its place.
- The markup nests: an element opened in a heading, a list item, a bold or
  an italic span and not closed there is closed at its end, with a warning;
  a `::` closes the last open element only in the same container (one
  inside a later bold or item closes nothing, with a warning at the `::`);
  an italic that would cross a bold, and a link label that would cross the
  end of a heading, an item or a bold, are left as text, with a warning.
  The HTML was malformed (`<li><span>...</li>...</span>`,
  `<strong><em>...</strong>...</em>`).
- The README starts with a two-minute sheet and one path, `lhtml.run(text)`;
  the macro functions, custom tags in Python, the document tree and the
  layout of the code move to `docs/advanced.md`. The CLI section says what one
  input and several inputs do without `-o`.
- Rules that hold for every tag (from an external review; LHTML 2 had the
  same surprises): the URL of a macro with `url:` is kept as written, as the
  one of `img::` (`demo::my__demo__.html`; `lhtml.Tag(..., url=True)` for a
  tag of the caller); in an attribute group `{...}`, a value quoted after
  its `=` holds its brackets (`{title="a } b"}`, see the attribute reader above; an
  apostrophe elsewhere is text); an attribute written in `{...}` replaces
  the one the tag or the macro gives (`img::a.png{alt="A"}`: one `alt`;
  `src`, `href` too; by its name, in any case, not by a word of a value);
  the CLI refuses, before writing anything, two inputs that would be
  written to the same file (`a/page.l.html` and `b/page.l.html` with `-o
  out/`, or names that differ by case only: one file on macOS or Windows).
  An input given twice, under any name, is converted once.
- A URL ends before a final `**` or `__` that closes a bold or an italic
  opened before its tag on its line: `**img::a.png**` is an image in bold
  (LHTML 2 put the `**` in its URL); `link::...#object.__init__` keeps its
  `__`. The same for `link::`, `video::` and the macros with `url:`.
- A nested list is inside the item before it, as HTML expects
  (`<li>a<ul>...</ul></li>`); LHTML 2 put it in an item of its own
  (`<li>a</li><li><ul>...</ul></li>`), which a page without a theme showed
  as a second bullet. It keeps an item of its own only when there is none
  to hold it (a list starting at `**`, a jump of two levels). The themes of
  the corpus draw no bullet: their renders are unchanged. An element left
  open in the text of an item (its `::` missing) ends where the nested list
  begins, not around it, with a warning.
- `line_breaks` (`-b`) is decided on the document tree: a line break of the source
  gets a `<br>` when its line and the next are not structure, a line being
  structure when the node at its start or its end is a block (a heading, a
  list, a block element, a code block, block raw HTML). The line breaks a
  tag writes in its own HTML get none: LHTML 2 wrote one into a style or an
  attribute written on two lines (breaking it), into a link label on two
  lines, and into the fallback text of a `video::`. An element is its
  opening, its children, its closing: the line breaks of its children get
  their `<br>`, except in a link (an `a` element of the tree), whose label
  is one label. The rules read the nodes (render.py): a block is a heading,
  a list, an item, a block element by its name, a code block, a raw zone
  that starts with a block tag; `<pre>` and `<textarea>` are an element of
  that name or a raw tag; no placeholder and no search in the HTML written.
- The character U+FDD0 (a Unicode noncharacter, the internal mark of the
  document tree) is replaced by U+FFFD in the input, as NUL already was.
- The CLI prints a problem as one line, `file:line:column: level: message`;
  `--wrapAuto` is `--wrap` (`-w` unchanged).
- An unknown language of a `code::` block is reported where the block starts.
- `videoplay::` adds `playsinline` to `autoplay loop muted`: on an iPhone,
  the video plays in the page instead of opening full screen.
- The CLI writes `\n` line endings on Windows too.

## [2.5.1] - 2026-10-04

### Fixed
- Chained classes `(.a.b#c)` give `class="a b" id="c"` (they gave
  `class="a.b#c"`); `(.a .b #c)` is unchanged.

## [2.5.0] - 2026-10-04

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- Macros: custom `::` tags declared in YAML or a dict (`tag`, `class`,
  `style`, `attrs`, `empty`, `url`, `variant`, `default`, `doc`), e.g.
  `box::(.good) ... ::`, `gap::l`, `demo::url`. They are declared with
  `lhtml -m file.yaml`, the `macros` key of the front matter (added to the
  others, `name: null` removes one) or of the `meta` of `lhtml.run()`, and
  are closed by `::` or `::name[-]`. A macro renders through the handler of
  its tag (`tag: img`, `video`, `videoplay`, `link` take their URL like
  `img::`), and invalid definitions raise `LHTMLMacroError`.
- New `lhtml.load_macros`, `register_macros`, `registry_with_macros`,
  `describe_macro` (what a definition renders, for documentation tools) and
  `LHTMLMacroError`.

## [2.4.1] - 2026-10-03

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- `lhtml --version` (`-V`) and `lhtml.__version__`. The version is defined
  once, in `lhtml/__init__.py`, and read from there by `pyproject.toml`.

### Changed
- A closing `::` (or `::name[-]`) without matching opening tag is kept as
  text in the output, instead of being replaced by `::??ERROR`. The
  `LHTMLWarning` is unchanged.

### Documentation
- README: explicit closing tags, list and code block outputs, Pygments
  stylesheet, `-w` output, using LHTML with Jinja2, default
  `directory_include`.

## [2.4.0] - 2026-10-03

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- Jinja2 expressions (`{{ ... }}`), statements (`{% ... %}`) and comments
  (`{# ... #}`) pass through unchanged, including quoted strings that contain
  the closing delimiter.
- `link::`, `img::`, `video::` and `videoplay::` accept Jinja expressions in
  their URL (`img::{{ base }}/photo.jpg`, `link::{{ url_for('page') }}[Home]`).
- HTML tags spanning multiple lines are protected like single-line tags.

### Changed
- Styles, classes/IDs and HTML attributes of LHTML tags (`[...]`, `(...)`,
  `{...}`) and heading `(.class #id)` groups are no longer formatted:
  `div::(.my__class__)` keeps `my__class__`. Link labels still support
  formatting.
- **Custom tag handlers:** the `[...]` group of a registered tag is no
  longer formatted (`alert::[**x**]` keeps `**x**`).
- Code and verbatim blocks share the left-to-right protection scan: a block
  marker inside a `<script>`, an HTML comment, an attribute, math or inline
  code is left untouched.
- Double quotes inside Jinja zones are not escaped in generated attributes.
- `process_title(text, stores=None)` replaces its previous signature
  (`stores` is optional).

### Fixed
- CLI: no input file of a batch is overwritten, including through symbolic
  or hard links.
- Line breaks option: only real `<pre>`/`<textarea>` tags disable `<br>`
  (not tag-like text in scripts, comments, attributes or Jinja, nor custom
  elements such as `<pre-view>`); multi-line Jinja statements are structure;
  `::#` comments no longer add an extra newline.
- A closing `::` inside a Jinja string no longer closes a tag.
- No exponential or quadratic slowdown on unclosed `{{` / `{%`.
- `videoplay::`: no double space in the generated `<video>` tag.

### Removed
- Unused `meta` options `add_title_id`, `wrap-custom-pre` and
  `wrap-custom-post` (they had no effect).
- `process_blocks_to_index` (internal, unused), the legacy test runner and
  the `ansicolors` dev dependency.

## [2.3.0] - 2026-10-03

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- Line breaks option (`-b` / `--line-breaks`, `line-breaks: true` in the
  front matter or `meta['line-breaks']`): source line breaks are rendered as
  `<br>`, except around block elements and inside code, verbatim, scripts,
  comments, math, `<pre>` and `<textarea>`.
- `LHTMLWarning` for unclosed tags and unmatched `::`, quoting the tag.

### Changed
- Raw zones are never transformed: HTML comments, `<script>`/`<style>`,
  inline code, URLs of `link::`/`img::`/`video::`, math and HTML tags are
  protected before comments and includes are handled.
- Inline code: `<` and `>` are escaped; no bold, italic, math or include
  inside.
- Tag names accept digits, `_` and `-`; tags glued to a word (`a[::2]`,
  `std::a::b`) are left untouched.
- YAML front matter only at the start of the document (safe load); the front
  matter of included files is ignored.
- Files are read and written as UTF-8 (BOM accepted); CRLF input is
  normalized.

### Fixed
- `::` at the very start of a document, nested brackets in tag groups,
  closing `::` followed by punctuation or HTML, colon runs (`::::`,
  `:::nl`), `<span>::</span>` in pre-highlighted code.
- `link::#anchor` is not a comment; `include::` inside code blocks inserts
  raw code; nested includes are resolved relative to the including file;
  circular includes raise `LHTMLIncludeLoopError`.
- Unknown or empty code language falls back to plain text.
- CLI: one failing file no longer stops the batch (errors on stderr, exit
  code 1), the output directory is created, input files are never
  overwritten.
- Title, css and js are escaped in the HTML wrapper.

## [2.2.0] - 2026-04-10

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- Explicit closing tags: `::div[-]`, `::span[-]`, etc.
- Improved error reporting.

## [2.1.0] - 2026-04-10

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- The CLI accepts several input files.

## [2.0.1] - 2026-04-10

### Added
- `parse(text, warn=False)` and `document.problems`: the problems of a text
  without the warnings module. Each parse collects its own (in threads
  too: no global state is changed, where `warnings.catch_warnings` was);
  an `LHTMLError` holds those found before it (`problems`) and its `path`.
  A warning emitted names the place of the caller, not of LHTML.
- `lhtml.highlight(code, language)`: the HTML of a code block.
- Type hints on the API, and `py.typed`; the API is `lhtml.__all__`, the
  modules inside the package may change in any release (README,
  Stability).
- GitHub URLs on the PyPI page.

## [2.0.0] - 2026-04-10

### Changed
- Rewrite: Lark-based tag parser, processing pipeline, plugin system
  (`TagRegistry` for custom `::` tags, `LexerRegistry` for syntax
  highlighters), structured errors with source positions.
- Packaged as `lhtml-markup` on PyPI with an `lhtml` command.

### Fixed
- Headings without parentheses (`= Title`).
- `::#` comments are removed on every line.

[2.4.1]: https://github.com/drohmer/lhtml/releases/tag/v2.4.1
[2.4.0]: https://github.com/drohmer/lhtml/releases/tag/v2.4.0
[2.3.0]: https://github.com/drohmer/lhtml/releases/tag/v2.3.0
