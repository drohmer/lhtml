#!/usr/bin/env python3

import os
import argparse
import re

import lhtmlLib

  
meta_default = {
  'wrap-auto': False,
  'add_title_id': False,
  'title': 'Webpage',
  'css': [],
  'js': [],
  'wrap-custom-pre': '',
  'wrap-custom-post': '',
  'directory_include': [os.getcwd()+'/'],  
}

def analyse_tag(text_in):

  return lhtmlLib.extract_bracket_elements(text_in, text_in.find('::')+2)
  



def read_yaml(text_in):
  _, yaml_parameter = lhtmlLib.process_yaml(text_in)
  return yaml_parameter

def run(text, meta_arg={}):

  meta = {**meta_default, **meta_arg}


  # Extract yaml inline variables
  text, meta_yaml = lhtmlLib.process_yaml(text)
  meta = {**meta, **meta_yaml}

  verbatim_index_store = []
  code_index_store = []
  found_include = True
  nbr_iteration = 0
  current_directory = ''
  if 'current_directory' in meta:
    current_directory = meta['current_directory']

  # Handle verbatim, comments and includes
  while found_include:
    text = lhtmlLib.process_verbatim_to_index(text, verbatim_index_store)
    text = lhtmlLib.process_remove_comment(text)
    text, found_include = lhtmlLib.process_include(text, meta['directory_include'])
    nbr_iteration = nbr_iteration+1
    if nbr_iteration>20:
      print('ERROR: Too many include iteration, stop loop')
      found_include = False

  text = lhtmlLib.remove_element_to_index(text, r'code::(.*?)code::\[-\]','code', code_index_store)

  # Handle per line elements
  text = lhtmlLib.process_title(text)
  text = lhtmlLib.process_listing(text)

  # Handle standard inline elements
  text = lhtmlLib.process_bold(text)
  text = lhtmlLib.process_italic(text)
  text = lhtmlLib.process_tag(text, current_directory)
  
  # Fill back code
  text = lhtmlLib.insert_element_from_index(text, r'code::\[(.*?)\]', code_index_store)
  text = lhtmlLib.process_code(text)

  # Fill back verbatim
  text = lhtmlLib.process_verbatim_back_from_index(text, verbatim_index_store)


  if meta['wrap-auto']==True:
    text = lhtmlLib.wrap_auto(text, meta)

  return text





if __name__== '__main__':
  parser = argparse.ArgumentParser(description='Lightweight HTML')
  parser.add_argument('inputFile', help='Input filepath')
  parser.add_argument('-w','--wrapAuto', help='Wrap content in basic HTML template', action='store_true')
  parser.add_argument('-o','--outputFile', help='Output filepath')
  args = parser.parse_args()  

  meta_main = {}
  if args.wrapAuto==True:
    meta_main['wrap-auto']=True

  meta_main['directory_include'] = [os.getcwd()+'/']
  f_in = args.inputFile
  if os.path.isfile(f_in):

    dir_to_include = os.path.dirname(f_in)
    if len(dir_to_include)>0:
      meta_main['directory_include'].append(os.getcwd()+'/'+dir_to_include+'/')
    
    with open(f_in) as fid_in:
      txt_in = fid_in.read()
      if txt_in[-1]!='\n':
        txt_in = txt_in+'\n'

      html = run(txt_in, meta_main)

      if html[-1]!='\n':
        html = html+'\n'
      if args.outputFile:
        with open(args.outputFile,'w') as f_out:
          f_out.write(html)
      else:
        print(html)
  
  else:
    print(f"Error: unrecognized input file [{f_in}]")