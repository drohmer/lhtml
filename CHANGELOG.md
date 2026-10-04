# Changelog

All notable changes to LHTML (`lhtml-markup` on PyPI) are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
