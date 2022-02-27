import io
import re

def analyse_listing(line):
  regex = "^(\*+) (.*)"
  match = re.search(regex,line)
  if match!=None:
      level = len(match.group(1))
      content = match.group(2)+'\n'
  else:
      level = 0
      content = line
  return {'level':level, 'content':content}

def process_listing(text):
  structure = []

  #print(text)
  buf = io.StringIO(text) 
  line = buf.readline()
  while line:
    structure.append( analyse_listing(line) )
    line = buf.readline()


  listing_adoc = ''
  level = 0
  for k,line in enumerate(structure):
  
    while level<line['level']:
        level = level+1
        if level>1:
            listing_adoc += '<li>\n'
        listing_adoc += '<ul>\n'
    
    if level>0:
        listing_adoc += '<li>\n'

    listing_adoc += line['content']

    if level>0:
        listing_adoc += '</li>\n'

    if k<len(structure)-1 and structure[k+1]['level']<level:
        while level>structure[k+1]['level']:
            level = level-1
            listing_adoc += '</ul>\n'
            if level>=1:
                listing_adoc += '</li>\n'
    if k==len(structure)-1:
        while level>0:
            level = level-1
            listing_adoc += '</ul>\n'
            if level>=1:
                listing_adoc += '</li>\n'

  return listing_adoc
