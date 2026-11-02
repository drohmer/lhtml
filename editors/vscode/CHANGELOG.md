# Changelog

## 0.1.1

Closer to how LHTML reads a page:

- an image in a link label (`link::page.html[img::thumb.png]`) no longer takes the `]` into its
  URL, and a URL leaves a final `**` or `__` to the bold or italic it closes (`**img::a.png**`);
- the groups `(...)`, `[...]` and `{...}` are read in any order (`::[...](.border)`,
  `videoplay::clip.mp4{poster="..."}[...]`), their brackets highlighted, a style may hold one
  nested `[...]`, attributes a `'...'` value or Jinja;
- `name::word::` (`gap::l::`, `span::word::`) is a tag; a `::` between two HTML tags is text;
- a lone `code::[-]` no longer opens a code block to the end of the file; a code block takes
  spaces around its language and groups after it (`code::[ python ](.x)`), and its `code::[-]`
  may end a line of code; `code::[markdown]` is mapped to Markdown;
- `$$` is not math (LHTML reads it as text); a title and an item need a space after `=` or `*`;
  an empty inline code ``` `` ``` is inline code;
- Jinja in a `[...]` style; `<script>` and `<style>` are JavaScript and CSS for comments and
  brackets;
- folding: a `std::cout` line in a code block, `gap::` and `gap::l` open no fold;
- the language configuration is valid JSON (its word pattern had an invalid escape).

## 0.1.0

First version: highlighting of LHTML (titles, items, bold, italic, inline code, the `::` system and
its groups, `link::`, `img::`, `video::`, `videoplay::`, code blocks in their language), of the HTML
around it, of Jinja and of math; folding of the `::` blocks and code blocks; snippets.
