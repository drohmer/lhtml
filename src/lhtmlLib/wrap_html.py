
def wrap_auto(html_in, meta):
  html_out  = ""
  html_out += "<!DOCTYPE html>\n"
  html_out += "\n"
  html_out += '<html lang="en">\n\n'
  html_out += '<head>\n'
  html_out += '\t<meta charset="utf-8">\n'
  html_out += '\t<meta name="viewport" content="width=device-width, initial-scale=1">\n'
  html_out += '\t<title>'+meta['title']+'</title>\n'
  if 'css' in meta:
    meta_css = meta['css']
    if isinstance(meta_css, str):
      meta_css = [meta_css]
    if isinstance(meta_css, list):
      for css_entry in meta_css:
        html_out += f'\t<link rel="stylesheet" type="text/css" href="{css_entry}">\n'

  if 'js' in meta:
    meta_js = meta['js']
    if isinstance(meta_js, str):
      meta_js = [meta_js]
    if isinstance(meta_js, list):
      for js_entry in meta_js:
        html_out += f'\t<script src="{js_entry}" defer></script>\n'

  html_out += '</head>\n\n'
  html_out += '<body>\n'
  html_out += html_in+"\n"
  html_out += '</body>\n\n'
  html_out += '</html>\n'

  return html_out