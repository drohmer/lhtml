import re
import os

import yaml

from .element_extract import *
from .export_html import *
from .listing import *
from .code import *






def process_verbatim_to_index(text, verbatim_index_store):

  new_text = ''
  index_previous = 0

  r_verbatim = r'verbatim::\[\](.*?)verbatim::\[-\]'
  regex = re.compile(r_verbatim,  re.DOTALL | re.MULTILINE)
  match = re.finditer(regex, text)
  for it in match:

    content = text[it.span()[0]+len('verbatim::[]'):it.span()[1]-len('verbatim::[-]')]
    verbatim_index = len(verbatim_index_store)
    verbatim_index_store.append(content)

    # replace content of verbatim
    new_text += text[index_previous:it.span()[0]]
    new_text += f'verbatim::[{verbatim_index}]'
    index_previous = it.span()[1]

  new_text += text[index_previous:]

  return new_text

def process_verbatim_back_from_index(text, verbatim_index_store):
  new_text = ''
  index_previous = 0

  r_verbatim = r'verbatim::\[(.*?)\]'
  match = re.finditer(r_verbatim, text)
  for it in match:
    index = int(it.group(1))
    content = verbatim_index_store[index]

    new_text += text[index_previous:it.span()[0]]
    new_text += content
    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text

def process_remove_comment(text):
  new_text = ''
  index_previous = 0

  r_comment = r'::#(.*?)$'
  match = re.finditer(r_comment, text)
  for it in match:
    new_text += text[index_previous:it.span()[0]]+'\n'
    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text

def find_file(directories, filename):

  for d in directories:
    pathname = d+filename
    if os.path.isfile(pathname):
      return d+filename
  
  print(f"Error could not find file [{filename}] in all possible directories {directories}")
  exit()

def process_include(text, directory):

  found_include = False
  new_text = ''
  index_previous = 0

  r_include = r'include::'
  match = re.finditer(r_include, text)
  for it in match:
    found_include = True
    element = extract_bracket_elements(text, it.span()[0]+len('include::'))
    
    
    filename = find_file(directory, element['text'])

    with open(filename,'r') as fid:
      text_to_add = fid.read()

    new_text += text[index_previous:it.span()[0]]
    new_text += text_to_add
    index_previous = element['index_end']
  
  new_text += text[index_previous:]

  return (new_text,found_include)

def process_code_inline(text):
  new_text = ''
  index_previous = 0

  r_code = r'`(.*?)`'
  match = re.finditer(r_code, text)
  for it in match:
    new_text += text[index_previous:it.span()[0]]
    text_to_add = it.group(0)[1:-1]
    new_text += f'<code class="code-inline">{text_to_add}</code>'
    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text


def process_bold(text):
  new_text = ''
  index_previous = 0

  r_bold = r'\*\*(.*?)\*\*'
  match = re.finditer(r_bold, text)
  for it in match:
    new_text += text[index_previous:it.span()[0]]
    text_to_add = it.group(0)[2:-2]
    new_text += f'<strong>{text_to_add}</strong>'
    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text

def process_italic(text):
  new_text = ''
  index_previous = 0

  r_italic = r'__(.*?)__'
  match = re.finditer(r_italic, text)
  for it in match:
    text_to_add = it.group(0)[2:-2]

    new_text += text[index_previous:it.span()[0]]
    new_text += f'<em>{text_to_add}</em>'

    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text


def export_tag_element_to_html(element, tag_to_close, current_directory=''):
  tag = element['tag']
  html = ''
  if tag=='div' or tag=='span':
    html = export_html_generic(element, tag, tag_to_close)
  elif tag == 'link':
    html = export_html_link(element)
  elif tag == 'img':
    html = export_html_img(element)
  elif tag == 'video':
    html = export_html_video(element,'', current_directory)
  elif tag == 'videoplay':
    html = export_html_video(element, 'autoplay loop muted', current_directory)
  elif tag == '':
    if check_is_closing_tag(element):
      if not len(tag_to_close)>0:
        print('Warning!! - closing tag: no element to close')
        print('Element error: ',element)
        return ('::??ERROR', True)

      html = '</'+tag_to_close.pop()+">"
    elif element['text']=='nl':
        html = '<div style="height:1em;"></div>'
    elif element['[]']!='' or element['()'] or element['{}'] or element['text']!='':
      html = export_html_generic(element, 'div', tag_to_close)
    else:
      return ('', False)
  else:
    return ('', False)
  return (html, True)

def process_tag(text, current_directory=''):
  new_text = ''
  index_previous = 0
  tag_to_close = []

  r_tag = r'::'
  match = re.finditer(r_tag, text)
  for it in match:
    if it.span()[0]>index_previous: # do not overlap previously treated element
      element = extract_bracket_elements(text, it.span()[0]+len(r_tag))
      html, is_real_tag = export_tag_element_to_html(element, tag_to_close, current_directory)
      tag = element['tag']
      index_end = element['index_end']

      if is_real_tag:
        index_start = it.span()[0]-len(tag)
        new_text += text[index_previous:index_start]
        new_text += html
      else:
        new_text += text[index_previous:index_end]
      index_previous = index_end

  new_text += text[index_previous:]

  return new_text




def process_title(text):
  new_text = ''
  index_previous = 0

  r_title = r'^(=+)\(?(.*?)\) (.*?)$'
  regex_title = re.compile(r_title,  re.DOTALL | re.MULTILINE)
  match = re.finditer(regex_title, text)
  for it in match:
    
    n = str(len(it.group(1)))
    class_id= it.group(2)
    title = it.group(3)
    
    if len(class_id) == 0:
      html = f'<h{n}>{title}</h{n}>\n'
    else:
      class_id_txt = export_html_element_class_and_id(class_id)
      html = f'<h{n} {class_id_txt}>{title}</h{n}>\n'

   

    new_text += text[index_previous:it.span()[0]]
    new_text += html

    index_previous = it.span()[1]
  new_text += text[index_previous:]
  return new_text

def process_code(text):
  new_text = ''
  index_previous = 0

  r_code = r'code::(.*?)code::\[-\]'
  regex_code = re.compile(r_code,  re.DOTALL | re.MULTILINE)
  match = re.finditer(regex_code, text)
  for it in match:
    element = extract_bracket_elements(text, it.span()[0]+len("code::"))
    code = text[element['index_end']:it.span()[1]-len('code::[-]')]
    language = element['[]']
    html = export_html_code(code, language)

    new_text += text[index_previous:it.span()[0]]
    new_text += html
    index_previous = it.span()[1]
  new_text += text[index_previous:]
  return new_text


def process_yaml(text):

  yaml_regex = '^---\n(.*?)\n---$'
  regex = re.compile(yaml_regex, re.DOTALL | re.MULTILINE)
  match = re.search(regex, text)
  if match:
    new_text = text[:match.span()[0]]
    new_text += text[match.span()[1]:]

    yaml_text = match.group(1)
    yaml_content = yaml.load(yaml_text, Loader=yaml.FullLoader)
  else:
    new_text = text
    yaml_content = {}


  return (new_text, yaml_content)