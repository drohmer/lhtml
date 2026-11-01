# LHTML for Visual Studio Code

Syntax highlighting, folding and snippets for [LHTML](https://scholartools.fr/lhtml/), the light
markup over HTML, and for the pages of [lhtml-site](https://github.com/drohmer/lhtml-site).

![LHTML in VS Code](images/preview.png)

## What it does

- **Highlighting of the LHTML marks**: titles `=`, items `*`, bold `**` and italic `__`, inline
  code, and the `::` system with its groups: classes and id `(.note #intro)`, a style `[...]`
  highlighted as CSS, attributes `{...}`. `link::`, `img::`, `video::` and `videoplay::` show their
  URL and label.
- **Everything else is HTML**, highlighted as HTML: tags, `<style>`, `<script>`, comments.
- **Code blocks** `code::[python]` ... `code::[-]` are highlighted in their language (Python, C++,
  JavaScript, shell, JSON, YAML, CSS, HTML, LaTeX...), and nothing in them is read as LHTML.
- **Jinja** `{{ ... }}`, `{% ... %}` and `{# ... #}`, also inside HTML attributes.
- **Math** `\( ... \)`, `\[ ... \]` and `$$ ... $$`.
- **Folding** of the blocks opened by `name::` or `::[...]` and closed by `::`, and of code blocks.
- **Snippets**: `div::`, `span::`, `cols`, `link::`, `img::`, `video::`, `videoplay::`, `code::`,
  `{% for`.

The rules follow LHTML: `std::vector`, `obj.link::x` or the slice `a[::2]` stay text.

## Files

The extension applies to:

- `*.l.html` and `*.lhtml`, the files of the `lhtml` command;
- `index.html.j2` under a `src/` directory: the pages of an lhtml-site project.

For other files, choose **LHTML** in the language picker of the status bar, or associate them in
your settings:

```json
"files.associations": {
  "*.html.j2": "lhtml"
}
```

## Install

From the Marketplace: search **LHTML** in the Extensions view.

From the repository:

```bash
cd editors/vscode
npx @vscode/vsce package
code --install-extension lhtml-*.vsix
```

## License

MIT, like LHTML.
