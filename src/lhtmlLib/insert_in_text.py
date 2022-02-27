import re

def insert_element_from_index(text, regex_to_insert, index_store):
  new_text = ''
  index_previous = 0

  match = re.finditer(regex_to_insert, text)
  for it in match:
    index = int(it.group(1))
    content = index_store[index]

    new_text += text[index_previous:it.span()[0]]
    new_text += content
    index_previous = it.span()[1]
  new_text += text[index_previous:]

  return new_text


def remove_element_to_index(text, regex_to_remove, name_to_store, index_store):
  new_text = ''
  index_previous = 0

  regex = re.compile(regex_to_remove,  re.DOTALL | re.MULTILINE)
  match = re.finditer(regex, text)
  for it in match:
    content_to_remove = text[it.span()[0]:it.span()[1]]
    index = len(index_store)
    index_store.append(content_to_remove)

    # replace content of code
    new_text += text[index_previous:it.span()[0]]
    new_text += f'{name_to_store}::[{index}]'
    index_previous = it.span()[1]

  new_text += text[index_previous:]
  return new_text