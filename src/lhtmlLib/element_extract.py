def pursue_for_enclosing(enclosing, text, idx):
  char_begin = enclosing[0]
  char_end = enclosing[1]
  assert(text[idx]==char_begin)

  level=0
  end_loop = False
  
  while end_loop!=True:
    idx = idx+1
    current = text[idx]
    if level==0 and current==char_end:
      end_loop=True
    else:
      if current==char_begin:
        level = level+1
      if current==char_end:
        level = level-1
    assert idx!=len(text)
  
  return idx
    

def extract_bracket_elements(text, index_start):

  elements = {'[]':"", '{}':"", '()':"", "text":"", "tag":"", "index_start":index_start, 'index_end':index_start}
  lut_tag = {'[':'[]', '(':'()', '{':'{}'}

  #get element before
  idx = index_start-2
  current_char = text[idx]
  #(current_char.isalpha() or current_char==':')
  while (current_char.isalpha() or current_char==':') and current_char!='\n' and idx>0:
  #while current_char!=' ' and current_char!='\n' and idx>0:
    idx = idx-1
    current_char = text[idx]
  
  if idx==0: # special case if the beginning of the file
    idx = -1
  elements['tag'] = text[idx+1:index_start-2]
  elements['index_start'] = idx+1


  already_met_text = False
  text_finished = False
  element_finished = False

  #get element after
  if index_start<len(text):
    idx = index_start
    current_char = text[idx]
    while current_char!=' ' and current_char!='\n' and element_finished==False:
      if current_char=='[' or current_char=='{' or current_char=='(':
        tag = lut_tag[current_char]
        idx = pursue_for_enclosing( tag , text, idx)
        if len(elements[tag])>0:
          elements[tag] = elements[tag] + ' '
        elements[tag] = elements[tag] + text[index_start+1:idx]

        idx = idx+1
        if idx<len(text):
          current_char = text[idx]
          index_start = idx
        else:
          element_finished=True

        if already_met_text==True:
          text_finished=True
      else:
        if text_finished==False:
          elements["text"] = elements["text"]+text[idx]
          already_met_text = True

          idx = idx+1
          current_char=text[idx]
          index_start = idx
        else:
          element_finished = True
    elements['index_end'] = idx

  return elements