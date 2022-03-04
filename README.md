# LHTML - Lightweight HTML Parser

LHTML is a simple and efficient way to write HTML with embedded CSS style.

LHTML inspires largely from markdown but focus on allowing more freedom to parameterize the style of the display. LHTML principle is the following:
* Everything written in LHTML is by default HTML. No modification is applied on raw HTML input.
* Only a few keywords and symbols (::, *, _, =) are used to trigger some specific conversions to ease document writing (nested listing, bold, italic, image, videos, etc.) bypassing the need to write HTML tags explicitly.
* CSS Style and classes with _div_ containers are easily added in the document with the same flexibility than raw HTML.

## Basic text-like conversion

_LHTML Input (similar to markdown)_
```
= A title
== A subtitle

* A list
** Sublist A
** Sublist B
*** Subsublist
** Sublist C

A word in **bold** or __italic__.
```

_HTML Output_
```
<h1> A title </h1>
<h2> A subtitle </h2>

<ul>
<li>A list
  <ul>
  <li>Sublist A</li>
  <li>Sublist B</li>
  <ul>
    <li>Subsublist</li>
  </ul>
  <li>Sublist C</li>
  </ul>
</li>
</ul>

A word in <strong>bold</strong> or <em>italic</em>.
```

## CSS style embedding

```
::[color:red; font-size:120%;]
This text is big and red.
::

img::somePic.jpg[width:400px;]

::(.myClass)[font-style:italic;]
* span::(.current) value 1 ::
* value 2
::

```

```
<div style="color:red; font-size:120%;">
This text is big and red.
</div>

<img style="width:400px;" src="somePic.jpg">

<div class=".myClass" style="font-style:italic;">
  <ul>
  <li> <span class="current"> value 1 </span> </li>
  <li> value 2 </li>
  </ul>
</div>
```

## Element syntax

Generic input
```
tagName::(.classNames #idNames)[cssStyle]{inlineValues} Content ::
```

Output
```
<tagName class="classNames" id="idNames" style="cssStyle" inlineValues> Content </tagName>
```

* If tagName is omited, the element is a div
```
::(.a) Content ::
=> <div class="a"> Content </div>
```

* The (optional) elements within () are classes and ID. 
```
::(.a .b #c #d) Content ::
=> <div class="a b" id="c d"> Content </div>
```


* The (optional) elements within [] are CSS style. 
```
::[color:red; border: 2px solid black;] Content ::
=> <div style="color:red; border: 2px solid black;"> Content </div>
```

* The (optional) elements within {} are raw inputs placed in the tag. 
```
::{muted controls} Content ::
=> <div muted controls> Content </div>
```

* Some special elements such as link, img, video also have a url
```
link::url Click ::
=> <a href="url"> Click ::
```

```
video::urlVideo.mp4{autoplay loop muted}
=> 
<video autoplay loop muted>
    <source src="assets/urlVideo.mp4" type="video/mp4">
    Cannot play video assets/urlVideo.mp4
</video>
```

## LHTML usage

### In command line

```
lhtml.py [-w] inputFile [-o outputFile]

-w --wrapAuto: Auto wrap the content in standard HTML header
-o outputFile: Optional output in text file
```

### Python API function

```python
import lhtml

lhtml.run(text, meta_arg={})
```

Default meta arguments
```python
meta_default = {
  'wrap-auto': False,
  'add_title_id': False,
  'title': 'Webpage',
  'css': [],
  'js': [],
  'title': '',
  'wrap-custom-pre': '',
  'wrap-custom-post': '',
  'directory_include': [os.getcwd()+'/'],  
}
```