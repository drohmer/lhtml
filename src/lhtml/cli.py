"""LHTML command-line interface.

The HTML goes to stdout (one input, no -o), every message to stderr: a
problem is `file:line:column: level: message`, with an excerpt of the line
in a terminal (lhtml/diagnostics.py). Writing files ends with a summary
(-q: none; -v: each file written).

The destinations are computed, then checked (an input missing, two inputs
to one file, an output that is an input or under a file: nothing is
written), then each file is converted and written.

Usage:
    lhtml [-w] file.l.html                       # Single file → stdout
    lhtml [-w] file.l.html -o output.html         # Single file → output file
    lhtml [-w] a.l.html b.l.html                  # Multiple files → .html next to sources
    lhtml [-w] a.l.html b.l.html -o build/        # Multiple files → output directory
    lhtml -b file.l.html                          # Source line breaks rendered as <br>
    lhtml -m macros.yaml file.l.html              # Custom :: tags declared in a YAML file
    lhtml --version
    python -m lhtml [same options]

Exit status: 0, 1 when a file is not converted or not written, 2 for a
wrong use of the command.
"""

import argparse
import os
import sys
import warnings

from . import __version__
from .diagnostics import Diagnostic, Reporter, shown_path
from .errors import LHTMLError
from .macros import load_macros, registry_with_macros
from .pipeline import run
from .process import read_source
from .wrap_html import wrap


def _ensure_trailing_newline(text):
    if text and text[-1] != '\n':
        return text + '\n'
    return text


def output_path(input_path, output_arg, several=False):
    """The file an input is written to: <dir>/<name>.html when `output_arg`
    is a directory (or ends with /, or several inputs share it), the file
    `output_arg`, or <name>.html next to the input (None). Creates nothing."""
    name, _ = os.path.splitext(os.path.basename(input_path))
    if name.endswith('.l'):         # page.l.html → page.html
        name = name[:-2]
    if output_arg is None:
        return os.path.join(os.path.dirname(input_path), name + '.html')
    if several or os.path.isdir(output_arg) or output_arg.endswith(('/', os.sep)):
        return os.path.join(output_arg, name + '.html')
    return output_arg


def _identity(path):
    info = os.stat(path)
    return info.st_dev, info.st_ino


def _blocking_file(path):
    """The file (not a directory) a directory of `path` would have to be."""
    directory = os.path.dirname(os.path.abspath(path))
    while directory and not os.path.exists(directory):
        directory = os.path.dirname(directory)
    return directory if directory and not os.path.isdir(directory) else None


def plan(inputs, output_arg):
    """[(input, output)], an input given twice (under any name) once; output
    None: stdout."""
    if len(inputs) == 1 and output_arg is None:
        return [(inputs[0], None)]
    jobs, seen = [], set()
    for f_in in inputs:
        key = _identity(f_in) if os.path.isfile(f_in) else ('missing', f_in)
        if key not in seen:
            seen.add(key)
            jobs.append((f_in, output_path(f_in, output_arg, several=len(inputs) > 1)))
    return jobs


def check(jobs, read=()):
    """The diagnostics that stop everything before a file is written;
    `read`: the other files the run reads (its macro files)."""
    problems, targets = [], {}
    inputs = {_identity(f) for f in [f for f, _ in jobs] + list(read) if os.path.isfile(f)}
    for f_in, out in jobs:
        if not os.path.exists(f_in):
            problems.append(Diagnostic(f_in, 'error', 'file not found'))
            continue
        if not os.path.isfile(f_in):
            problems.append(Diagnostic(f_in, 'error', 'not a file'))
            continue
        if out is None:
            continue
        if os.path.exists(out) and _identity(out) in inputs:
            problems.append(Diagnostic(f_in, 'error', f'its output would overwrite the input file {out}'))
            continue
        if os.path.isdir(out):
            problems.append(Diagnostic(f_in, 'error', f'its output {out} is a directory'))
            continue
        blocking = _blocking_file(out)
        if blocking:
            problems.append(Diagnostic(f_in, 'error', f'cannot write {out}: {shown_path(blocking)} is a file'))
            continue
        # one file for both: names that differ by case only (macOS, Windows),
        # or two existing names of one file (a hard link)
        keys = [os.path.realpath(out).casefold()] + ([_identity(out)] if os.path.exists(out) else [])
        other = next((targets[key] for key in keys if key in targets), None)
        if other is not None:
            problems.append(Diagnostic(f_in, 'error', f'{other} and {f_in} would both be written '
                                                      f'to {out}'))
            continue
        targets.update((key, f_in) for key in keys)
    return problems


def convert(source, macros, line_breaks, wrapped):
    """(its HTML, its warnings in the order of the file)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        html = run(_ensure_trailing_newline(source), macros=macros, line_breaks=line_breaks)
    if wrapped:
        html = wrap(html)
    found = sorted((w.message for w in caught),
                   key=lambda m: (getattr(m, 'line', None) or 0, getattr(m, 'column', None) or 0))
    return _ensure_trailing_newline(html), found


def main(argv=None):
    """CLI entry point."""
    parser = argparse.ArgumentParser(prog='lhtml', description='Lightweight HTML')
    parser.add_argument('input', nargs='+', help='Input file(s)')
    parser.add_argument('-w', '--wrap', action='store_true',
                        help='Wrap content in basic HTML template')
    parser.add_argument('-b', '--line-breaks', action='store_true',
                        help='Render the line breaks of the source text as <br>')
    parser.add_argument('-m', '--macros', action='append', metavar='FILE',
                        help='YAML file of macros (custom :: tags); may be repeated')
    parser.add_argument('-o', '--output',
                        help='Output file (single input) or directory (multiple inputs)')
    parser.add_argument('-q', '--quiet', action='store_true', help='No summary')
    parser.add_argument('-v', '--verbose', action='store_true', help='Name each file written')
    parser.add_argument('-V', '--version', action='version', version=f'lhtml {__version__}')
    if sys.stderr is None:              # closed: argparse would write its usage to stdout
        sys.stderr = open(os.devnull, 'w')
    args = parser.parse_args(argv)

    if args.output == '':
        parser.error('-o: an empty name')
    if (len(args.input) > 1 and args.output is not None
            and not os.path.isdir(args.output) and not args.output.endswith(('/', os.sep))):
        parser.error(f'-o must be a directory when several input files are given '
                     f'(got {args.output!r}; add a trailing / to create it)')

    reporter = Reporter(sys.stderr)
    macros = None
    if args.macros:
        try:
            macros = load_macros(args.macros)
            registry_with_macros(macros)    # checked before any file
        except LHTMLError as e:
            place = getattr(e, 'path', None) or (args.macros[0] if len(args.macros) == 1 else 'lhtml')
            message = str(e).removesuffix(f' [{place}]')
            reporter.report(Diagnostic(shown_path(place), 'error', message, e.line, e.column))
            sys.exit(1)

    jobs = plan(args.input, args.output)
    problems = check(jobs, args.macros or ())
    if problems:
        for problem in problems:
            reporter.report(Diagnostic(shown_path(problem.path), problem.level, problem.message))
        if any(out is not None for _, out in jobs):
            reporter.write(reporter.paint('lhtml: nothing written', 'error'))
        sys.exit(1)

    converted = failed = 0
    for f_in, out in jobs:
        shown = shown_path(f_in)
        source = None
        try:
            source = read_source(f_in)
            html, found = convert(source, macros, args.line_breaks, args.wrap)
        except (LHTMLError, OSError, UnicodeError) as e:
            reporter.report(Diagnostic.of(shown, 'error', e), source)     # its line, when it has one
            failed += 1
            continue
        for warning in found:
            reporter.report(Diagnostic.of(shown, 'warning', warning), source)
        if out is None:
            try:
                sys.stdout.buffer.write(html.encode('utf-8'))
                sys.stdout.flush()
            except (AttributeError, OSError) as e:       # no stdout, or a pipe closed (| head)
                if isinstance(e, BrokenPipeError):
                    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())   # no error at exit
                    sys.exit(1)
                reporter.report(Diagnostic(shown, 'error', 'cannot write the standard output'))
                failed += 1
                continue
            converted += 1
            continue
        try:
            directory = os.path.dirname(out)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(out, 'w', encoding='utf-8', newline='') as f_out:
                f_out.write(html)
        except OSError as e:
            reporter.report(Diagnostic.of(shown, 'error', e))
            failed += 1
            continue
        converted += 1
        if args.verbose:
            reporter.write(reporter.paint(f'{shown} {reporter.symbol("→", "->")} {shown_path(out)}', 'dim'))

    if not args.quiet and any(out is not None for _, out in jobs):
        reporter.write(reporter.summary(converted, failed))
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
