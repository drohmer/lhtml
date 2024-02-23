import pygments
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

from pygments.lexer import RegexLexer, words, inherit
from pygments.token import *
import re


#this should be externalized as a plugin
class CustomCppLexer(pygments.lexers.CppLexer):

    tokens = {
        'statements': [
            (words(('vec3','vec2','vec4','mat2','mat3','mat4', 'numarray_stack', 'numarray', 'mesh', 'mesh_drawable', 'rotation_transform', 'affine_rt', 'affine_rts', 'affine', 'quaternion', 'string', 'ostream'), suffix=r'\b'), Keyword.Type),
            (words(('dot', 'cross', 'norm', 'normalize', 'draw', 'draw_wireframe', 'transpose', 'det', 'inverse'), suffix=r'\b'), Keyword.Function),
            (r'gl\w*', Keyword.Function),
            (r'const\&', Number),
            (r'std::', Number),
            (r'cgp::', Number),
            inherit,
        ]
    }



def export_html_code(text, language, is_linenos=False, cssclass='code'):

    lexer = get_lexer_by_name(language, stripall=False, stripnl=True, ensurenl='True', tabsize=2, encoding='utf-8')
    formatter = HtmlFormatter(is_linenos=False, cssclass="code")
    html = highlight(text, lexer, formatter)

    if language=='c++':
        html = highlight(text, CustomCppLexer(), formatter)

    return html