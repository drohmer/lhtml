from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter


def export_html_code(text, language, is_linenos=False, cssclass='code'):

    lexer = get_lexer_by_name(language, stripall=False, stripnl=True, ensurenl='True', tabsize=2, encoding='utf-8')
    formatter = HtmlFormatter(is_linenos=False, cssclass="code")
    html = highlight(text, lexer, formatter)

    return html