# Changelog

All notable changes to LHTML (`lhtml-markup` on PyPI) are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.0.0] - Unreleased

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
  caller: `title`, `css`, `js`, `line-breaks`, `macros`, `wrap-auto` in the
  meta).
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
  `lhtml.TAGS`; custom ones are given to the run, `lhtml.run(text, meta,
  tags={...})`; the lexers are a dict, `lhtml.LEXERS`;
  `registry_with_macros` returns a dict.
- `LHTMLTagStackError`, the positions of `LHTMLError` (`source_pos`,
  `source_line`) and `pos_to_line`: the messages quote the source instead.

The API is `run`, `parse`, `render`, `Tag`, `TAGS`, `LEXERS`, the macro
functions and the errors.

### Added
- `media`, a key of the meta of `lhtml.run()`: a callable,
  `media(src) -> [(url, mime type)]`, listing the sources of a video. An
  empty list, or no resolver, keeps the source as written. It is read from
  the meta given by the caller only, not from the front matter.
- `line` and `column` on `LHTMLWarning` and `LHTMLError`: where the problem
  is in the text given to `run` (1-based, `None` when not known, as for a
  macros file). A tag element carries its `line` and `column` to the
  `render` of its tag.
- `lhtml.parse(text)` gives the document tree (headings, lists, bold,
  italic, `::` elements, and code, inline code, mathematics, raw HTML as
  leaves), every node with its place (`span` in the text given, `line`,
  `column`); `lhtml.render(document)` its HTML. `lhtml.run` is both: the
  text passes are gone. The tree is walked and rendered without recursion,
  and a text of unclosed brackets is read in linear time (it was
  quadratic).

### Changed
- A tag is an `lhtml.Tag(render, container)`: `render(element, children,
  context)` returns its HTML, closing tag included, and `container` says
  whether it holds what follows. The handlers `(element, tag_to_close,
  context) -> (html, is_real_tag)` are gone; `lhtml.TAGS` (now read-only)
  and `registry_with_macros` give Tags. A tag given to `run` wins over the
  built-in tags and the macros, the anonymous `::` div included; its name
  is checked, and an exception of its `render` becomes an `LHTMLError` with
  its place. `render` receives the `ProcessingContext` of the run as its
  third argument (`context.meta`, `context.media`).
- The markup nests: an element opened in a heading, a list item, a bold or
  an italic span and not closed there is closed at its end, with a warning;
  a `::` closes the last open element only in the same container (one
  inside a later bold or item closes nothing, with a warning at the `::`);
  an italic that would cross a bold, and a link label that would cross the
  end of a heading, an item or a bold, are left as text, with a warning.
  The HTML was malformed (`<li><span>...</li>...</span>`,
  `<strong><em>...</strong>...</em>`).
- `line-breaks` is decided on the document tree: a line break of the source
  gets a `<br>` when its line and the next are not structure, a line being
  structure when the node at its start or its end is a block (a heading, a
  list, a block element, a code block, block raw HTML). The line breaks a
  tag writes in its own HTML get none: LHTML 2 wrote one into a style or an
  attribute written on two lines (breaking it), into a link label on two
  lines, and into the fallback text of a `video::`.
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
- Explicit closing tags: `::div[-]`, `::span[-]`, etc.
- Improved error reporting.

## [2.1.0] - 2026-04-10

### Added
- The CLI accepts several input files.

## [2.0.1] - 2026-04-10

### Added
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
