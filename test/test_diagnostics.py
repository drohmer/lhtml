"""The diagnostics: what a stream cannot write is escaped, never lost."""

import io
import os

import pytest

from lhtml import cli
from lhtml.diagnostics import Diagnostic, Reporter, shown_path


def _ascii_stream():
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(raw, encoding='ascii')


@pytest.mark.parametrize('rich', [False, True])
def test_an_accent_on_an_ascii_stream_is_escaped(rich):
    raw, stream = _ascii_stream()
    reporter = Reporter(stream, rich=rich, color=False)
    reporter.report(Diagnostic('été.l.html', 'error', 'problème ici', 1, 3), 'déjà vu\n')
    reporter.report(Diagnostic('b.l.html', 'warning', 'second'))
    stream.flush()
    shown = raw.getvalue().decode('ascii')
    assert '\\xe9t\\xe9.l.html:1:3: error: probl\\xe8me ici' in shown
    assert 'b.l.html: warning: second' in shown     # the next one is shown too
    assert reporter.stream is stream


def test_utf8_streams_are_written_as_they_are():
    stream = io.StringIO()
    Reporter(stream, rich=False, color=False).report(Diagnostic('été.l.html', 'error', 'problème'))
    assert stream.getvalue() == 'été.l.html: error: problème\n'


def test_a_stream_that_cannot_encode_what_it_did_not_declare():
    class Latin(io.StringIO):           # declares no encoding, writes ASCII only
        def write(self, text):
            text.encode('ascii')
            return super().write(text)
    stream = Latin()
    Reporter(stream, rich=False, color=False).report(Diagnostic('é', 'error', 'x'))
    assert stream.getvalue() == '\\xe9: error: x\n'


def test_a_closed_stream_stops_the_writes_not_the_run():
    stream = io.StringIO()
    stream.close()
    reporter = Reporter(stream, rich=False, color=False)
    reporter.report(Diagnostic('a', 'error', 'x'))
    reporter.report(Diagnostic('b', 'error', 'y'))
    assert reporter.stream is None and reporter.counts['error'] == 2


def test_a_path_on_another_drive_stays_absolute(monkeypatch):
    def relpath(path, start=None):
        raise ValueError('path is on mount C:, start on mount D:')
    monkeypatch.setattr(os.path, 'relpath', relpath)
    assert shown_path(os.path.abspath('x.l.html')) == os.path.abspath('x.l.html')


def test_the_exit_code_does_not_depend_on_the_stream(tmp_path, monkeypatch):
    page = tmp_path / 'été.l.html'
    page.write_text('include::missing.html\n', encoding='utf-8')
    codes = []
    for encoding in ('ascii', 'utf-8'):
        raw = io.BytesIO()
        monkeypatch.setattr('sys.stderr', io.TextIOWrapper(raw, encoding=encoding))
        monkeypatch.setattr('sys.stdout', io.StringIO())
        monkeypatch.setattr('sys.argv', ['lhtml', str(page)])
        with pytest.raises(SystemExit) as stop:
            cli.main()
        codes.append(stop.value.code)
        import sys
        sys.stderr.flush()
        assert 'missing.html' in raw.getvalue().decode(encoding)
    assert codes == [1, 1]


@pytest.mark.parametrize('encoding', ['latin-1', 'iso8859-15', 'cp1252'])
def test_an_encoding_that_has_the_accent_shows_it(encoding):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=encoding)
    Reporter(stream, rich=True, color=False).report(Diagnostic('pagé.l.html', 'warning', 'x', 1, 1), 'é\n')
    stream.flush()
    assert raw.getvalue().decode(encoding).startswith('pagé.l.html:1:1: warning: x\n  1 | é')


def test_a_file_whose_name_starts_with_two_dots_is_here():
    assert shown_path(os.path.abspath('..foo.l.html')) == '..foo.l.html'
    assert shown_path(os.path.abspath(os.path.join(os.pardir, 'x'))).startswith(os.sep)


def test_without_stderr_the_usage_is_not_on_stdout(monkeypatch, capsys):
    monkeypatch.setattr('sys.stderr', None)
    monkeypatch.setattr('sys.argv', ['lhtml'])
    with pytest.raises(SystemExit) as stop:
        cli.main()
    assert stop.value.code == 2 and capsys.readouterr().out == ''


def _cli(monkeypatch, args, stdin=b''):
    out, err = io.BytesIO(), io.StringIO()
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(stdin), encoding='utf-8'))
    monkeypatch.setattr('sys.stdout', io.TextIOWrapper(out, encoding='utf-8'))
    monkeypatch.setattr('sys.stderr', err)
    monkeypatch.setattr('sys.argv', ['lhtml', *args])
    code = 0
    try:
        cli.main()
    except SystemExit as stop:
        code = stop.code
    import sys
    sys.stdout.flush()
    return code, out.getvalue().decode('utf-8'), err.getvalue()


def test_the_standard_input(monkeypatch, tmp_path):
    assert _cli(monkeypatch, ['-'], '﻿**a**\n'.encode()) == (0, '<strong>a</strong>\n', '')
    code, _, err = _cli(monkeypatch, ['-'], b'div:: x\n')
    assert code == 0 and err.startswith('<stdin>:1:1: warning: div:: is never closed')
    out = tmp_path / 'a.html'
    assert _cli(monkeypatch, ['-', '-o', str(out)], b'= T\n')[0] == 0 and out.read_text() == '<h1>T</h1>\n\n'


def test_the_standard_input_alone_and_to_a_file(monkeypatch, tmp_path):
    (tmp_path / 'b.l.html').write_text('x')
    assert _cli(monkeypatch, ['-', str(tmp_path / 'b.l.html'), '-o', str(tmp_path) + '/'])[0] == 2
    assert _cli(monkeypatch, ['-', '-o', str(tmp_path) + '/'])[0] == 2


def test_the_options_of_a_document_imply_it(monkeypatch):
    code, out, _ = _cli(monkeypatch, ['-', '--title', 'Notes', '--css', 'a.css', '--css', 'b.css'], b'x\n')
    assert code == 0 and out.startswith('<!DOCTYPE html>') and '<title>Notes</title>' in out
    assert out.count('rel="stylesheet"') == 2


def test_the_help_says_the_exit_status(monkeypatch):
    code, out, _ = _cli(monkeypatch, ['--help'])
    assert code == 0 and 'exit status:' in out and '- for the standard input' in out
