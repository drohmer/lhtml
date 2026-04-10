"""LHTML test suite.

Tests cover:
- Input/output reference pairs (regression tests)
- Heading syntax (with and without class/id)
- Comment removal
- Plugin system (tag registry, lexer registry)
- Non-regression on real-world lab_website examples
"""

import os
import glob
import warnings

import pytest

import lhtml
from lhtml.pipeline import ProcessingPipeline, TagRegistry, LexerRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INPUT_DIR = os.path.join(os.path.dirname(__file__), 'input_tests')
META = {'directory_include': [INPUT_DIR + '/']}


def _find_test_pairs():
    """Find all .l.html / -out.html test pairs."""
    pairs = []
    for f in sorted(os.listdir(INPUT_DIR)):
        if f.endswith('.l.html'):
            ref = f.replace('.l.html', '-out.html')
            ref_path = os.path.join(INPUT_DIR, ref)
            if os.path.isfile(ref_path):
                pairs.append((f, ref))
    return pairs


# ---------------------------------------------------------------------------
# Reference pair tests (replaces run_test.py)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('input_file,ref_file', _find_test_pairs(),
                         ids=[p[0] for p in _find_test_pairs()])
def test_reference_pair(input_file, ref_file):
    """Each .l.html input should produce output matching -out.html."""
    meta = dict(META)

    with open(os.path.join(INPUT_DIR, input_file)) as f:
        txt = f.read()
    with open(os.path.join(INPUT_DIR, ref_file)) as f:
        expected = f.read()

    if input_file.endswith('.w.l.html'):
        meta['wrap-auto'] = True

    result = lhtml.run(txt, meta)

    # Reference files have trailing newline
    assert result == expected[:-1] or result == expected


# ---------------------------------------------------------------------------
# Heading tests
# ---------------------------------------------------------------------------

class TestHeadings:
    def test_simple_title(self):
        assert '<h1>Hello</h1>' in lhtml.run('\n= Hello\n')

    def test_h2(self):
        assert '<h2>Sub</h2>' in lhtml.run('\n== Sub\n')

    def test_h3(self):
        assert '<h3>Deep</h3>' in lhtml.run('\n=== Deep\n')

    def test_with_class(self):
        r = lhtml.run('\n=(.myClass) Styled\n')
        assert '<h1 class="myClass">Styled</h1>' in r

    def test_with_id(self):
        r = lhtml.run('\n=(#myId) IDed\n')
        assert '<h1 id="myId">IDed</h1>' in r

    def test_with_class_and_id(self):
        r = lhtml.run('\n=(.cls #id) Both\n')
        assert 'class="cls"' in r
        assert 'id="id"' in r

    def test_parentheses_in_content(self):
        r = lhtml.run('\n= Exemples de (très bons) projets\n')
        assert '<h1>Exemples de (très bons) projets</h1>' in r


# ---------------------------------------------------------------------------
# Comment tests
# ---------------------------------------------------------------------------

class TestComments:
    def test_inline_comment(self):
        r = lhtml.run('\nSome text ::# this is a comment\n')
        assert '::# this' not in r
        assert 'Some text' in r

    def test_full_line_comment(self):
        r = lhtml.run('\n::# full line comment\nAfter\n')
        assert '::# full' not in r
        assert 'After' in r

    def test_multiple_comments(self):
        r = lhtml.run('\nA ::# c1\nB ::# c2\nC\n')
        assert 'A' in r
        assert 'B' in r
        assert 'C' in r
        assert '::# c1' not in r
        assert '::# c2' not in r


# ---------------------------------------------------------------------------
# Inline formatting tests
# ---------------------------------------------------------------------------

class TestInlineFormatting:
    def test_bold(self):
        assert '<strong>bold</strong>' in lhtml.run('\n**bold**\n')

    def test_italic(self):
        assert '<em>italic</em>' in lhtml.run('\n__italic__\n')

    def test_inline_code(self):
        assert '<code class="code-inline">x</code>' in lhtml.run('\n`x`\n')

    def test_nested_bold_italic(self):
        r = lhtml.run('\n**bold with __italic__ inside**\n')
        assert '<strong>' in r
        assert '<em>italic</em>' in r


# ---------------------------------------------------------------------------
# Tag system tests
# ---------------------------------------------------------------------------

class TestTags:
    def test_div_with_style(self):
        r = lhtml.run('\ndiv::[color:red;] hello ::\n')
        assert '<div style="color:red;"> hello </div>' in r

    def test_link(self):
        r = lhtml.run('\nlink::https://example.com[Click]\n')
        assert '<a href="https://example.com">Click</a>' in r

    def test_img(self):
        r = lhtml.run('\nimg::pic.jpg[width:100px;]\n')
        assert 'src="pic.jpg"' in r
        assert 'alt="pic.jpg"' in r

    def test_spacer(self):
        r = lhtml.run('\n::nl\n')
        assert '<div style="height:1em;"></div>' in r

    def test_passthrough_std_namespace(self):
        r = lhtml.run('\nstd::vector<float>\n')
        assert 'std::vector<float>' in r

    def test_passthrough_trick(self):
        r = lhtml.run('\ntrick::\n')
        assert 'trick::' in r


# ---------------------------------------------------------------------------
# Verbatim tests
# ---------------------------------------------------------------------------

class TestVerbatim:
    def test_verbatim_protects_content(self):
        r = lhtml.run('\nverbatim::[]\n**not bold**\nverbatim::[-]\n')
        assert '<strong>' not in r
        assert '**not bold**' in r


# ---------------------------------------------------------------------------
# Plugin system tests
# ---------------------------------------------------------------------------

class TestPluginSystem:
    def test_custom_tag_handler(self):
        registry = TagRegistry()
        registry.register('alert', lambda el, ts, cd: (
            f'<div class="alert">{el.get("text", "")}</div>', True
        ))
        pipeline = ProcessingPipeline(registry=registry)
        r = pipeline.run('\nalert::Warning\n')
        assert '<div class="alert">Warning</div>' in r

    def test_custom_lexer_registry(self):
        reg = LexerRegistry()
        reg.register('test-lang', object)  # dummy
        assert reg.get('test-lang') is object
        assert reg.get('unknown') is None

    def test_tag_registry_list(self):
        reg = TagRegistry()
        reg.register('foo', lambda e, t, c: ('', False))
        reg.register('bar', lambda e, t, c: ('', False))
        assert set(reg.registered_tags()) == {'foo', 'bar'}


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

class TestCodeBlocks:
    def test_python_code_block(self):
        r = lhtml.run('\ncode::[python]\ndef hello():\n    pass\ncode::[-]\n')
        assert '<pre>' in r
        assert 'hello' in r

    def test_cpp_code_block(self):
        r = lhtml.run('\ncode::[c++]\nint x = 0;\ncode::[-]\n')
        assert '<pre>' in r

    def test_text_code_block(self):
        r = lhtml.run('\ncode::[text]\nplain text\ncode::[-]\n')
        assert 'plain text' in r


# ---------------------------------------------------------------------------
# Unnamed div (::() syntax)
# ---------------------------------------------------------------------------

class TestUnnamedDiv:
    def test_unnamed_div_with_class(self):
        r = lhtml.run('\n::(.highlight)[padding:10px;]\ncontent\n::\n')
        assert 'class="highlight"' in r
        assert 'style="padding:10px;"' in r
        assert 'content' in r

    def test_unnamed_div_style_only(self):
        r = lhtml.run('\n::[color:red;]\ntext\n::\n')
        assert '<div style="color:red;">' in r

    def test_unnamed_div_wrapping_list(self):
        r = lhtml.run('\n::(.box)\n* item one\n* item two\n::\n')
        assert 'class="box"' in r
        assert '<ul>' in r
        assert '<li>' in r


# ---------------------------------------------------------------------------
# Inline close (:: on same line)
# ---------------------------------------------------------------------------

class TestInlineClose:
    def test_empty_div_inline_close(self):
        r = lhtml.run('\ndiv::[height:25px;]::\n')
        assert '<div style="height:25px;"></div>' in r

    def test_span_inline_close_with_class(self):
        r = lhtml.run('\nspan::(.tag)[color:white;] label ::\n')
        assert '<span class="tag" style="color:white;"> label </span>' in r

    def test_unnamed_inline_close(self):
        r = lhtml.run('\n::[margin:5px;]::\n')
        assert '<div style="margin:5px;"></div>' in r


# ---------------------------------------------------------------------------
# Complex nesting
# ---------------------------------------------------------------------------

class TestComplexNesting:
    def test_nested_divs_three_levels(self):
        r = lhtml.run('\n::[padding:20px;]\n::[background:#eee;]\ndiv::[color:red;] deep ::\n::\n::\n')
        assert '<div style="padding:20px;">' in r
        assert '<div style="background:#eee;">' in r
        assert '<div style="color:red;"> deep </div>' in r
        assert r.count('</div>') == 3

    def test_formatting_inside_nested_div(self):
        r = lhtml.run('\n::[border:1px solid;]\n**bold** and __italic__\n::\n')
        assert '<strong>bold</strong>' in r
        assert '<em>italic</em>' in r
        assert '<div style="border:1px solid;">' in r

    def test_link_inside_div(self):
        r = lhtml.run('\n::[padding:5px;]\nlink::https://example.com[click]\n::\n')
        assert '<a href="https://example.com">click</a>' in r


# ---------------------------------------------------------------------------
# Mixed content (real-world patterns)
# ---------------------------------------------------------------------------

class TestMixedContent:
    def test_heading_with_bold(self):
        r = lhtml.run('\n= Title with **bold** word\n')
        assert '<h1>Title with <strong>bold</strong> word</h1>' in r

    def test_list_with_inline_code(self):
        r = lhtml.run('\n* Use `printf` to print\n')
        assert '<li>' in r
        assert '<code class="code-inline">printf</code>' in r

    def test_list_with_link(self):
        r = lhtml.run('\n* See link::https://example.com[docs]\n')
        assert '<li>' in r
        assert '<a href="https://example.com">docs</a>' in r

    def test_code_inside_styled_div(self):
        r = lhtml.run('\n::[font-size:80%;]\ncode::[c++]\nint x;\ncode::[-]\n::\n')
        assert '<div style="font-size:80%;">' in r
        assert '<pre>' in r

    def test_raw_html_passthrough_with_lhtml(self):
        r = lhtml.run('\n<p>HTML</p>\ndiv::[color:red;] lhtml ::\n')
        assert '<p>HTML</p>' in r
        assert '<div style="color:red;"> lhtml </div>' in r


# ---------------------------------------------------------------------------
# Non-regression: real-world lab_website examples
# ---------------------------------------------------------------------------

class TestLabWebsite:
    @pytest.fixture
    def lab_files(self):
        base = os.path.join(
            os.path.dirname(__file__), '..', '..', 'examples_references',
            'lab_website', 'csc_43043_ep_lab_website', '_site', 'content',
        )
        files = glob.glob(os.path.join(base, '**', '*.l.html'), recursive=True)
        return files

    def test_all_lab_files_compile(self, lab_files):
        if not lab_files:
            pytest.skip('Lab website examples not found')
        for f in lab_files:
            with open(f) as fid:
                txt = fid.read()
            if not txt.endswith('\n'):
                txt += '\n'
            meta = {'directory_include': [os.path.dirname(f) + '/']}
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                html = lhtml.run(txt, meta)
            assert len(html) > 0, f'Empty output for {f}'
