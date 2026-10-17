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
import warnings

from .errors import LHTMLMacroError, LHTMLWarning
from .export_html import TAGS, _attr, _build_attrs, export_html_generic


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


def make_handler(name, spec):
    """Tag handler (see export_html.TAGS) for one macro definition: the element
    of its tag, with the defaults of the macro (classes, attributes) added to
    those of the source."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    void = tag.lower() in VOID_TAGS
    classes = (spec.get('class') or '').split()
    attrs = (spec.get('attrs') or '').strip()
    empty = bool(spec.get('empty', False))
    url = spec.get('url')
    variant = spec.get('variant')
    default = spec.get('default')

    def handler(element, tag_to_close, context):
        text = element['text']
        all_classes = list(classes)
        if variant:
            value = text.strip()
            closed = value.endswith('::')          # gap::l:: (closed at once)
            if closed:
                value = value[:-2].strip()
            value = value or (str(default) if default is not None else '')
            if value:
                if value not in [str(v) for v in variant]:
                    warnings.warn(f'{name}::{value}: unknown variant (expected one of '
                                  f'{", ".join(str(v) for v in variant)}) '
                                  f'near {element.get("context", "")!r}',
                                  LHTMLWarning, stacklevel=4)
                all_classes.append(f'{classes[0]}-{value}')
            text = '::' if closed else ''
        inline = ' '.join(a for a in (attrs, element['{}']) if a)
        if url:
            closed = text.rstrip().endswith('::')
            value = text.rstrip()[:-2] if closed else text
            inline = ' '.join(a for a in (f'{url}="{_attr(value.strip())}"', inline) if a)
            text = '::' if closed else ''
        merged = {**element,
                  '()': ' '.join(['.' + c for c in all_classes] + ([element['()']] if element['()'] else [])),
                  '{}': inline,
                  'text': text}
        if void:
            return f'<{tag}{_build_attrs(merged)}>' + ('' if text == '::' else text), True
        if empty and not merged['text'].endswith('::'):
            merged['text'] += '::'   # closed at once
        return export_html_generic(merged, tag, tag_to_close), True

    return handler


def describe_macro(name, spec):
    """What a macro definition gives, for documentation tools: its opening
    HTML, the attribute its text sets (url), whether it has no content
    (empty), its variants (a list, True for any, or None) and default, doc."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    html = '<' + tag
    if spec.get('class'):
        html += f' class="{_attr(spec["class"])}"'
    if spec.get('attrs'):
        html += ' ' + spec['attrs'].strip()
    variant = spec.get('variant')
    return {'html': html + '>',
            'url': spec.get('url'),
            'empty': bool(spec.get('empty')) or tag.lower() in VOID_TAGS,
            'variants': [str(v) for v in variant] if variant else None,
            'default': None if spec.get('default') is None else str(spec['default']),
            'doc': spec.get('doc')}


def load_macros(source):
    """Macro definitions from a dict, a YAML file name, or a list of them
    (later definitions replace earlier ones, and a definition null removes
    the macro). A dict or file holds the definitions, directly or as its
    only key 'macros'."""
    return {name: spec for name, spec in _load_macros(source).items() if spec is not None}


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
            raise LHTMLMacroError(f'cannot read macros file [{source}]: {e}') from e
        except yaml.YAMLError as e:
            raise LHTMLMacroError(f'invalid YAML in macros file [{source}]: {e}') from e
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


def registry_with_macros(macros, base=None):
    """The tag handlers of `base` (the built-in TAGS by default) plus those of
    the macros (see load_macros): a new dict, `base` is not changed."""
    handlers = dict(TAGS if base is None else base)
    for name, spec in load_macros(macros).items():
        handlers[name] = make_handler(name, spec)
    return handlers
