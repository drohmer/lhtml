import re
import os


default_cache_video_directory = 'cache_video_codecs/'

def export_html_element_style(text):
  if len(text)==0:
    return ''
  return ' style=\"'+text+'\"'


def export_html_element_class_and_id(text):
  #input: ".nameOfClass .nameOfClass2 #nameID #nameID2"
  #output: class="nameOfClass nameOfClass2" id="nameID nameID2"

  if len(text)==0:
    return ""

  html_class = ""
  html_id = ""
  token = text.split()
  for e in token:
    if e.startswith('.'):
      if len(html_class)>0:
        html_class += ' '
      html_class += e[1:]
    if e.startswith('#'):
      if len(html_class)>0:
        html_id += ' '
      html_id += e[1:]
  html = ""
  if len(html_class)>0:
    html += ' class=\"' + html_class + '\"'
  if len(html_id)>0:
    html += ' id=\"' + html_id + '\"'
  return html

def export_html_element_inline(text):
  if len(text)==0:
    return ''
  return ' '+text

def export_html_generic(elements, tag, tag_to_close):

  to_close = True
  html  = '<'+tag

  html += export_html_element_class_and_id(elements['()'])
  html += export_html_element_style(elements['[]'])
  html += export_html_element_inline(elements['{}'])
  
  html += '>'


  if len(elements['text'])>0:
    if elements['text'].endswith('::'):
      elements['text'] = elements['text'][:-2]
      to_close = False
    html += elements['text']
  
  if to_close==True:
    tag_to_close.append(tag)
  else:
    html += '</'+tag+'>'

  return html

def export_html_link(elements):
  html  = '<a'

  html += export_html_element_class_and_id(elements['()'])
  html += export_html_element_inline(elements['{}'])
  html += ' href=\"'+elements['text']+'\"'
  html += '>'

  html += elements['[]']

  html += '</a>'

  return html

def export_html_img(elements):
  html  = '<img'

  html += export_html_element_class_and_id(elements['()'])
  html += export_html_element_style(elements['[]'])
  html += export_html_element_inline(elements['{}'])
  html += ' src=\"'+elements['text']+'\"'
  html += ' alt=\"'+elements['text']+'\"'
  html += '>'

  return html


def export_html_video(elements, default_inline='', current_directory=''):

  source = elements['text']
  extension = source.split('.')[-1]

  candidate_poster = source.replace(f'.{extension}',f'-poster.jpg')

  html = '<video'

  html += export_html_element_inline(elements['{}'])
  if default_inline != '':
    html += ' '+default_inline+' ' 
  html += export_html_element_class_and_id(elements['()'])
  html += export_html_element_style(elements['[]'])

  if os.path.isfile(candidate_poster):
    html += f' poster="{candidate_poster}"'

  html += '>\n'






  source_name, source_extension = os.path.splitext(source)
  source_basename = os.path.basename(source_name)
  source_dirname = os.path.dirname(source_name)
  source_base_dirname = os.path.basename(source_dirname)

  cache_video_directory = default_cache_video_directory
  found_video_codecs = False
  if current_directory!='' and source_base_dirname=='assets':
    dir_video_codecs = source_dirname+'/'+cache_video_directory
    if os.path.isdir(current_directory+dir_video_codecs):
      attempt = dir_video_codecs+source_basename+'-vp9.webm'

      if os.path.isfile(current_directory+attempt):
        html += f'\t<source src="{attempt}" type="video/webm">\n'
        found_video_codecs = True

      attempt = dir_video_codecs+source_basename+'-h265.mp4'
      if os.path.isfile(current_directory+attempt):
        html += f'\t<source src="{attempt}" type="video/mp4">\n'
        found_video_codecs = True

      attempt = dir_video_codecs+source_basename+'-h264.mp4'
      if os.path.isfile(current_directory+attempt):
        html += f'\t<source src="{attempt}" type="video/mp4">\n'
        found_video_codecs = True

  if found_video_codecs == False:
    html += f'\t<source src="{source}" type="video/{extension}">\n'



  

  html += f'\t Cannot play video {source}\n'
  html += '</video>'


  return html



def check_is_closing_tag(elements):
  if elements['tag']=='' and elements['index_end']-elements['index_start']==2:
    return True
  return False



