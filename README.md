# LHTML - Lightweight HTML Parser

LHTML is a simple and efficient way to write HTML with embeded CSS.

## Command line usage

```
lhtml.py [-w] inputFile [-o outputFile]

-w --wrapAuto: Auto wrap the content in standard HTML header
-o outputFile: Optional output in text file
```

## Python function usage

```python
import lhtml

lhtml.run(text, meta_arg={}):
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