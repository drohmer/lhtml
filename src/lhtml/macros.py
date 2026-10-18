"""Macros: custom :: tags declared in a configuration (YAML file or dict).

A macro is a named shortcut for an HTML element with default classes and
attributes:

    macros:
      small:  {class: small}                     # small:: ... ::  -> <div class="small">
      credit: {tag: span, class: credit}
      gap:    {class: gap, empty: true, variant: [s, m, l], default: m}
      demo:   {tag: iframe, class: demo, empty: true, url: src}

Fields (all optional):
    tag      HTML element (default: div), rendered as it is: never through
             an LHTML tag (tag: video gives <video>, not video::)
    class    default classes, separated by spaces
    attrs    default HTML attributes, e.g. 'frameborder="0"'
    empty    the element has no content: it is closed immediately
             (gap::, demo::url) instead of waiting for a closing ::
             (always the case for HTML void elements such as br, hr)
    url      the text after :: is the value of this attribute (src,
             data-src, ...)
    variant  the list of the variants: the text after :: selects one,
             added as the class '<first class>-<variant>'
             (gap::l -> class="gap gap-l")
    default  variant used when none is given
    doc      description, for documentation (ignored)

The classes and attributes of the source are added to the defaults, and
its style is the style of the element
(box::(.good)[margin:0] -> <div class="box good" style="margin:0">).
A macro is closed by ::.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

from .errors import LHTMLMacroError
from . import attributes
from .attributes import Attributes, quoted
from .export_html import TAGS, Tag, _class_and_id, _words, assemble, join_styles
from .nodes import Element, Text, Written
from .errors import suggestion
from .process import _warn


NAME_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*$')
FIELDS = {'tag', 'class', 'attrs', 'empty', 'url', 'variant', 'default', 'doc'}
# HTML elements without closing tag (a macro using them is always empty)
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
             'source', 'track', 'wbr'}
BUILTIN_TAGS = ('div', 'span', 'link', 'img', 'video', 'videoplay', 'code',
                'include', 'nl')
RESERVED_NAMES = ('macros',)    # a file may hold its macros under 'macros:'
NOT_ELEMENTS = ('nl', 'code', 'include')     # LHTML tags that are not elements


def _check(name, spec):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise LHTMLMacroError(f'invalid macro name {name!r}')
    if name in BUILTIN_TAGS:
        raise LHTMLMacroError(f'macro {name!r} would replace a built-in tag')
    if name in RESERVED_NAMES:
        raise LHTMLMacroError(f'{name!r} is not a macro name (reserved)')
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        raise LHTMLMacroError(f'macro {name!r}: expected a mapping, got {type(spec).__name__}')
    unknown = set(spec) - FIELDS
    if unknown:
        raise LHTMLMacroError(f'macro {name!r}: unknown field(s) {", ".join(sorted(unknown))}')
    for key in ('tag', 'class', 'attrs', 'url'):
        if spec.get(key) is not None and not isinstance(spec[key], str):
            raise LHTMLMacroError(f'macro {name!r}: {key} must be a string, got {spec[key]!r}')
    if spec.get('empty') is not None and not isinstance(spec['empty'], bool):
        raise LHTMLMacroError(f'macro {name!r}: empty must be true or false, got {spec["empty"]!r}')
    tag = spec.get('tag') or 'div'
    if not NAME_RE.match(tag):
        raise LHTMLMacroError(f'macro {name!r}: invalid tag {tag!r}')
    if tag in NOT_ELEMENTS:
        raise LHTMLMacroError(f'macro {name!r}: {tag}:: is not an element (tag: {tag})')
    if spec.get('empty') is False and tag.lower() in VOID_TAGS:
        raise LHTMLMacroError(f'macro {name!r}: {tag} has no content (empty cannot be false)')
    if spec.get('url') is not None and not NAME_RE.match(spec['url']):
        raise LHTMLMacroError(f'macro {name!r}: url must be an attribute name, got {spec["url"]!r}')
    variant = spec.get('variant')
    if variant is not None and not isinstance(variant, list):
        raise LHTMLMacroError(f'macro {name!r}: variant must be a list')
    if isinstance(variant, list) and any(not isinstance(v, (str, int)) or isinstance(v, bool)
                                         for v in variant):
        raise LHTMLMacroError(f'macro {name!r}: the variants must be names')
    if spec.get('default') is not None and not isinstance(spec['default'], (str, int)):
        raise LHTMLMacroError(f'macro {name!r}: default must be a name')
    if isinstance(variant, list) and spec.get('default') is not None \
            and str(spec['default']) not in [str(v) for v in variant]:
        raise LHTMLMacroError(f'macro {name!r}: default {spec["default"]!r} is not one of the variants')
    if variant and spec.get('url'):
        raise LHTMLMacroError(f'macro {name!r}: variant and url cannot be combined')
    if variant and not str(spec.get('class', '')).split():
        raise LHTMLMacroError(f'macro {name!r}: a variant needs a class')
    return spec


def macro_tag(name, spec):
    """The Tag of one macro definition: the element of its tag, with the
    defaults of the macro (classes, attributes) added to those of the source."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    void = tag.lower() in VOID_TAGS
    classes = (spec.get('class') or '').split()
    empty = bool(spec.get('empty', False))
    url = spec.get('url')
    variant = spec.get('variant')
    default = spec.get('default')
    # its attrs, read once: their classes and styles come before those of the page
    given = Attributes.read((spec.get('attrs') or '').strip())
    attrs_classes = [word for value in given.values_of('class', nested=False) if value for word in _words(value)]
    styles = [value for value in given.values_of('style', nested=False) if value]
    given_empty = {name for name in ('class', 'style') if given.values_of(name, nested=False)}    # class="": kept
    given = given.without({'class', 'style'}, nested=False)     # one in a Jinja block stays there

    def build(written):
        word = written.text
        variant_class = []
        if variant:
            value = word.strip() or (str(default) if default is not None else '')
            if value:
                if value not in [str(v) for v in variant]:
                    names = [str(v) for v in variant]
                    _warn(f'{name}::{value}: unknown variant, expected one of {", ".join(names)}'
                          f'{suggestion(value, names)}', written, stacklevel=5)
                variant_class = [f'{classes[0]}-{value}']
            word = ''
        url_attribute = Attributes()
        if url:
            value = word.strip()
            if value or url not in given:     # demo:: keeps the src of the macro
                url_attribute = Attributes.read(f'{url}="{quoted(value)}"')
            word = ''
        page_classes, ids = _class_and_id(written.parentheses)
        # the macro, then its url, then the page: a later one replaces an attribute;
        # an id of the page (#id) replaces the macro's
        defaults, url_attribute, page = attributes.layered(
            given.without({'id'}) if ids else given, url_attribute, Attributes.read(written.braces))
        head, styled, rest = assemble(classes + variant_class + attrs_classes + page_classes, ids,
                                      join_styles(*styles, written.brackets),
                                      url_attribute.extend(defaults).extend(page), given_empty)
        node = Element(tag, head.extend(styled).extend(rest), void=void)
        if void:                        # the word after it is text
            return [node] + ([Text(word)] if word else [])
        if word:
            node.children.append(Text(word))
        return node

    return Tag(build, container=not void and not empty, url=bool(url))


def describe_macro(name: str, spec: Mapping | None) -> dict:
    """What a macro definition gives, for documentation tools: its opening
    HTML, the attribute its text sets (url), whether it has no content
    (empty), its variants (a list, or None) and default, doc."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    node = macro_tag(name, spec).build(Written(tag=name))
    attributes = (node[0] if isinstance(node, list) else node).attributes
    url = spec.get('url')
    if url and url in attributes and url not in Attributes.read(spec.get('attrs')):
        del attributes[url]             # the url given in the page
    variant = spec.get('variant')
    if variant and spec.get('default') is not None:     # its classes without the default variant
        attributes['class'] = ' '.join(c for c in attributes['class'].split()
                                       if c != f'{spec["class"].split()[0]}-{spec["default"]}')
    return {'html': f'<{tag}{attributes.html()}>',
            'url': url,
            'empty': bool(spec.get('empty')) or tag.lower() in VOID_TAGS,
            'variants': [str(v) for v in variant] if variant else None,
            'default': None if spec.get('default') is None else str(spec['default']),
            'doc': spec.get('doc')}


def load_macros(source: Mapping | str | os.PathLike | Iterable | None) -> dict[str, dict]:
    """Macro definitions from a dict, a YAML file name, or a list of them
    (later definitions replace earlier ones, and a definition null removes
    the macro). A dict or file holds the definitions, directly or as its
    only key 'macros'."""
    return {name: spec for name, spec in _load_macros(source).items() if spec is not None}


def _file_error(path, message, line=None, column=None):
    """An LHTMLMacroError of a macros file: `path` is where it is."""
    return LHTMLMacroError(f'{message} [{path}]', line, column, os.fspath(path))


def _load_macros(source):
    if source is None:
        return {}
    if isinstance(source, (list, tuple)):
        merged = {}
        for item in source:
            merged.update(_load_macros(item))
        return merged
    if isinstance(source, (str, os.PathLike)):
        import yaml
        try:
            with open(source, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except OSError as e:
            raise _file_error(source, f'cannot read the macros file: {e.strerror or e}') from e
        except UnicodeDecodeError as e:
            raise _file_error(source, 'the macros file is not UTF-8') from e
        except yaml.YAMLError as e:
            mark = getattr(e, 'problem_mark', None)
            problem = ' '.join(str(getattr(e, 'problem', None) or e).split())
            raise _file_error(source, f'invalid YAML in the macros file: {problem}',
                              *((mark.line + 1, mark.column + 1) if mark else ())) from e
        source = data
    if not isinstance(source, dict):
        raise LHTMLMacroError(f'macros: expected a mapping, got {type(source).__name__}')
    if set(source) == {'macros'}:
        macros = source['macros']
        if macros is None:
            return {}
        if not isinstance(macros, dict):
            raise LHTMLMacroError(f"macros: expected a mapping, got {type(macros).__name__}")
        return dict(macros)
    return dict(source)


def registry_with_macros(macros: Mapping | str | os.PathLike | Iterable | None,
                         base: Mapping[str, Tag] | None = None) -> dict[str, Tag]:
    """The tags of `base` (the built-in TAGS by default) plus those of the
    macros (see load_macros): a new dict, `base` is not changed."""
    tags = dict(TAGS if base is None else base)
    for name, spec in load_macros(macros).items():
        tags[name] = macro_tag(name, spec)
    return tags
