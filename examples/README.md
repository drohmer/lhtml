# LHTML Examples

Install LHTML (`pipx install lhtml-markup` for the command, or `pip install lhtml-markup` in a virtual environment; see [Installation](../README.md#installation)), then run the examples from this directory:

```shell
lhtml example_1.l.html                  # HTML on stdout
lhtml example_1.l.html -o example_1.html
lhtml example_1.l.html -w               # Full HTML document
lhtml example_1.l.html example_video.l.html   # example_1.html, example_video.html
lhtml -m macros.yaml slide.l.html lab_page.l.html --css style.css   # two complete pages
```

The first two show the syntax one construct at a time. `slide.l.html` and
`lab_page.l.html` are a slide and a lab page of a course, written as
recommended: each role is a macro of `macros.yaml` (`gap` for a vertical
space, `aside`, `center`, `caption`, `path`), and its look is in
`style.css`, one place to change it, rather than a style written again on
each page. What stays in a page is what belongs to it: the size of an
image, the position of a block on its slide.


## example_1.l.html

Headings, a list and a styled div:

```
= Main Title

== Subtitle

* First point
* Second point
* Third point

::[color:red;]
This text should be red
::
```

`lhtml example_1.l.html` generates:

```html
<h1>Main Title</h1>


<h2>Subtitle</h2>


<ul>
<li>
First point
</li>
<li>
Second point
</li>
<li>
Third point
</li>
</ul>

<div style="color:red;">
This text should be red
</div>
```


## example_video.l.html

An image and a video. `videoplay::` adds `autoplay loop muted playsinline`; the poster is an attribute written in `{}`:

```
img::assets/video-poster.jpg[width:400px;]

videoplay::assets/video.mp4{poster="assets/video-poster.jpg"}[width:400px;]
```

`lhtml example_video.l.html` generates:

```html
<img style="width:400px;" src="assets/video-poster.jpg" alt="assets/video-poster.jpg">

<video poster="assets/video-poster.jpg" autoplay loop muted playsinline style="width:400px;">
	<source src="assets/video.mp4" type="video/mp4">
	 Cannot play video assets/video.mp4
</video>
```


## slide.l.html

A slide: a title, a list, vertical spaces (`gap::`, `gap::l`), a block
placed on the slide (`aside::[top:150px; left:700px;]`), math kept for
KaTeX or MathJax (`\(p' = R(\theta)\,p\)`), and a centered video with
its caption:

```
center::
videoplay::assets/video.mp4[width:400px;]
caption:: Example of animation ::
::
```

gives `<div class="center">`, the video, then `<div class="caption"> Example
of animation </div>`: the caption is small, gray and italic by `style.css`.

The positions assume the size of a slide, which the theme of a deck gives
(see [lhtml-site](https://github.com/drohmer/lhtml-site)); in a plain page
the block is placed in the window. The math needs KaTeX or MathJax in the
page, as a deck or a site of lhtml-site loads them.


## lab_page.l.html

A lab page: the path of the code (`path::`), a paragraph `<p>` (a blank
line makes none), instructions as a list with math and inline code, a C++
code block, a link, and the expected result as a centered video with its
caption. The code is colored by a Pygments stylesheet
([Code Blocks](../README.md#code-blocks)), given with a second `--css`.

In a site of lhtml-site, the same content is the body of a page
`index.html.j2`, between `{% extends ... %}` and `{% block content %}`
... `{% endblock %}`, and the macros and their style come with the theme.
