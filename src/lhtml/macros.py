"""Macros: custom :: tags declared in a configuration (YAML file or dict).

A macro is a named shortcut for an HTML element with default classes,
style and attributes:

    macros:
      small:  {class: small}                     # small:: ... ::  -> <div class="small">
      credit: {tag: span, class: credit}
      gap:    {class: gap, empty: true, variant: [s, m, l], default: m}
      demo:   {tag: iframe, class: demo, empty: true, url: src}

Fields (all optional):
    tag      HTML element (default: div)
    class    default classes, separated by spaces
    style    default inline style, placed before the style of the source
    attrs    default HTML attributes, e.g. 'frameborder="0"'
    empty    the element has no content: it is closed immediately
             (gap::, demo::url) instead of waiting for a closing ::
             (always the case for HTML void elements such as br, hr)
    url      the text after :: is the value of this attribute (src, href)
    variant  the text after :: selects a variant, added as the class
             '<first class>-<variant>' (gap::l -> class="gap gap-l");
             a list restricts the allowed variants
    default  variant used when none is given

The classes, style and attributes of the source are added to the defaults
(box::(.good)[margin:0] -> <div class="box good" style="margin:0">).
A macro is closed by :: or by its name (::box[-]).
"""

from __future__ import annotations

import os
import re
import warnings

from .errors import LHTMLMacroError, LHTMLWarning
from .export_html import (
    _attr, export_html_element_class_and_id, export_html_element_inline,
    export_html_element_style,
)
from .pipeline import TagRegistry, tag_registry


NAME_RE = re.compile(r'[A-Za-z][A-Za-z0-9_-]*$')
FIELDS = {'tag', 'class', 'style', 'attrs', 'empty', 'url', 'variant', 'default', 'css', 'doc'}
# HTML elements without closing tag (a macro using them is always empty)
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
             'source', 'track', 'wbr'}
BUILTIN_TAGS = ('div', 'span', 'link', 'img', 'video', 'videoplay', 'code', 'verbatim',
                'include', 'nl')


class OpenTag(str):
    """HTML tag name on the stack of open tags, remembering the macro name
    so that ::name[-] closes it."""

    def __new__(cls, tag, name):
        obj = super().__new__(cls, tag)
        obj.name = name
        return obj


def _check(name, spec):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise LHTMLMacroError(f'invalid macro name {name!r}')
    if name in BUILTIN_TAGS:
        raise LHTMLMacroError(f'macro {name!r} would replace a built-in tag')
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        raise LHTMLMacroError(f'macro {name!r}: expected a mapping, got {type(spec).__name__}')
    unknown = set(spec) - FIELDS
    if unknown:
        raise LHTMLMacroError(f'macro {name!r}: unknown field(s) {", ".join(sorted(unknown))}')
    for key in ('tag', 'class', 'style', 'attrs', 'url'):
        if spec.get(key) is not None and not isinstance(spec[key], str):
            raise LHTMLMacroError(f'macro {name!r}: {key} must be a string, got {spec[key]!r}')
    if spec.get('empty') is not None and not isinstance(spec['empty'], bool):
        raise LHTMLMacroError(f'macro {name!r}: empty must be true or false, got {spec["empty"]!r}')
    tag = spec.get('tag') or 'div'
    if not NAME_RE.match(tag):
        raise LHTMLMacroError(f'macro {name!r}: invalid tag {tag!r}')
    if tag.lower() in VOID_TAGS and spec.get('empty') is False:
        raise LHTMLMacroError(f'macro {name!r}: <{tag}> has no content (empty cannot be false)')
    if spec.get('url') is not None and not NAME_RE.match(spec['url']):
        raise LHTMLMacroError(f'macro {name!r}: url must be an attribute name, got {spec["url"]!r}')
    variant = spec.get('variant')
    if variant is not None and not isinstance(variant, (bool, list)):
        raise LHTMLMacroError(f'macro {name!r}: variant must be true or a list')
    if isinstance(variant, list) and any(not isinstance(v, (str, int)) or isinstance(v, bool)
                                         for v in variant):
        raise LHTMLMacroError(f'macro {name!r}: the variants must be names')
    if spec.get('default') is not None and not isinstance(spec['default'], (str, int)):
        raise LHTMLMacroError(f'macro {name!r}: default must be a name')
    if variant and spec.get('url'):
        raise LHTMLMacroError(f'macro {name!r}: variant and url cannot be combined')
    if variant and not str(spec.get('class', '')).split():
        raise LHTMLMacroError(f'macro {name!r}: a variant needs a class')
    return spec


def make_handler(name, spec):
    """Tag handler (see TagRegistry) for one macro definition."""
    spec = _check(name, spec)
    tag = spec.get('tag') or 'div'
    void = tag.lower() in VOID_TAGS
    classes = str(spec.get('class', '') or '').split()
    style = str(spec.get('style', '') or '').strip()
    attrs = str(spec.get('attrs', '') or '').strip()
    empty = bool(spec.get('empty', False))
    url = spec.get('url')
    variant = spec.get('variant')
    default = spec.get('default')

    def handler(element, tag_to_close, current_directory):
        text = element['text']
        all_classes = list(classes)
        if variant:
            value = text.strip() or (str(default) if default is not None else '')
            if value:
                if isinstance(variant, list) and value not in [str(v) for v in variant]:
                    warnings.warn(f'{name}::{value}: unknown variant (expected one of '
                                  f'{", ".join(str(v) for v in variant)}) '
                                  f'near {element.get("context", "")!r}',
                                  LHTMLWarning, stacklevel=4)
                all_classes.append(f'{classes[0]}-{value}')
            text = ''
        source_classes = element['()']
        class_id = ' '.join(['.' + c for c in all_classes] + ([source_classes] if source_classes else []))
        full_style = ' '.join(s for s in (style, element['[]']) if s)

        html = f'<{tag}'
        if url:
            html += f' {url}="{_attr(text)}"'
            text = ''
        html += export_html_element_class_and_id(class_id)
        html += export_html_element_style(full_style)
        if attrs:
            html += ' ' + attrs
        html += export_html_element_inline(element['{}'])
        html += '>'

        if void:
            return html + text, True
        if empty:
            return html + text + f'</{tag}>', True
        if text.endswith('::'):
            return html + text[:-2] + f'</{tag}>', True
        tag_to_close.append(OpenTag(tag, name))
        return html + text, True

    return handler


def load_macros(source):
    """Macro definitions from a dict, a YAML file name, or a list of them
    (later definitions replace earlier ones). A dict or file may hold the
    definitions directly or under a top-level 'macros' key."""
    if source is None:
        return {}
    if isinstance(source, (list, tuple)):
        merged = {}
        for item in source:
            merged.update(load_macros(item))
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
    if 'macros' in source:
        if source['macros'] is None:
            return {}
        if not isinstance(source['macros'], dict):
            raise LHTMLMacroError(f"macros: expected a mapping, got {type(source['macros']).__name__}")
        source = source['macros']
    return dict(source)


def register_macros(macros, registry: TagRegistry | None = None):
    """Register macro definitions (see load_macros) in a tag registry
    (the global one by default). Returns the registry."""
    registry = registry if registry is not None else tag_registry
    for name, spec in load_macros(macros).items():
        registry.register(name, make_handler(name, spec))
    return registry


def registry_with_macros(macros, base: TagRegistry | None = None):
    """A new registry: the tags of `base` (global registry by default) plus the macros."""
    base = base if base is not None else tag_registry
    registry = TagRegistry()
    for name in base.registered_tags():
        registry.register(name, base.get(name))
    return register_macros(macros, registry)
