"""LHTML command-line interface.

Usage:
    lhtml [-w] file.l.html                       # Single file → stdout
    lhtml [-w] file.l.html -o output.html         # Single file → output file
    lhtml [-w] a.l.html b.l.html                  # Multiple files → .html next to sources
    lhtml [-w] a.l.html b.l.html -o build/        # Multiple files → output directory
    lhtml -b file.l.html                          # Source line breaks rendered as <br>
    lhtml -m macros.yaml file.l.html              # Custom :: tags declared in a YAML file
    lhtml --version
    python -m lhtml [same options]
"""

import os
import sys
import argparse
import warnings

from . import __version__
from .errors import LHTMLError
from .macros import load_macros, registry_with_macros
from .pipeline import ProcessingPipeline
from .process import read_source


_pipeline = ProcessingPipeline()


def _ensure_trailing_newline(text):
    if text and text[-1] != '\n':
        return text + '\n'
    return text


def _output_path_for(input_path, output_arg):
    """Determine the output path for a given input file.

    If output_arg is a directory, write <dir>/<basename>.html.
    If output_arg is a file path, return it directly (single-file mode).
    If output_arg is None, derive .html from the input path.
    """
    basename = os.path.basename(input_path)
    name, _ = os.path.splitext(basename)
    # Strip double extensions like .l.html → .html
    if name.endswith('.l'):
        name = name[:-2]

    if output_arg is None:
        # Write next to source
        return os.path.join(os.path.dirname(input_path), name + '.html')

    if os.path.isdir(output_arg) or output_arg.endswith('/'):
        os.makedirs(output_arg, exist_ok=True)
        return os.path.join(output_arg, name + '.html')

    # Treat as a direct file path (single-file mode)
    return output_arg


def _process_file(f_in, meta_base):
    """Process a single LHTML file and return (html, warning_messages).

    Includes are looked up first in the file's directory, then in the
    current directory.
    """
    meta = dict(meta_base)
    dir_of_file = os.path.dirname(os.path.abspath(f_in)) + '/'
    meta['directory_include'] = [dir_of_file] + [
        d for d in meta.get('directory_include', []) if d != dir_of_file]
    meta['current_directory'] = dir_of_file

    txt = _ensure_trailing_newline(read_source(f_in))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        html = _ensure_trailing_newline(_pipeline.run(txt, meta))
    return html, [str(w.message) for w in caught]


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Lightweight HTML')
    parser.add_argument('inputFiles', nargs='+', help='Input file(s)')
    parser.add_argument('-w', '--wrapAuto',
                        help='Wrap content in basic HTML template',
                        action='store_true')
    parser.add_argument('-b', '--line-breaks',
                        help='Render the line breaks of the source text as <br>',
                        action='store_true')
    parser.add_argument('-m', '--macros', action='append', metavar='FILE',
                        help='YAML file of macros (custom :: tags); may be repeated')
    parser.add_argument('-o', '--output',
                        help='Output file (single input) or directory (multiple inputs)')
    parser.add_argument('-V', '--version', action='version',
                        version=f'lhtml {__version__}')
    args = parser.parse_args()

    meta = {'directory_include': [os.getcwd() + '/']}
    if args.wrapAuto:
        meta['wrap-auto'] = True
    if args.line_breaks:
        meta['line-breaks'] = True
    if args.macros:
        try:
            meta['macros'] = load_macros([os.path.abspath(f) for f in args.macros])
            registry_with_macros(meta['macros'])  # validate before processing files
        except LHTMLError as e:
            print(f'lhtml: error: {e}', file=sys.stderr)
            sys.exit(1)

    single_file = len(args.inputFiles) == 1
    single_to_stdout = single_file and args.output is None

    if (not single_file and args.output is not None
            and not os.path.isdir(args.output) and not args.output.endswith('/')):
        parser.error(f'-o must be a directory when several input files are given '
                     f'(got {args.output!r}; add a trailing / to create it)')

    errors = 0
    for f_in in args.inputFiles:
        if not os.path.isfile(f_in):
            print(f'lhtml: error: file not found [{f_in}]', file=sys.stderr)
            errors += 1
            continue

        try:
            html, messages = _process_file(f_in, meta)
            for message in messages:
                print(f'lhtml: warning in {f_in}: {message}', file=sys.stderr)

            if single_to_stdout:
                sys.stdout.buffer.write(html.encode('utf-8'))
                sys.stdout.flush()
                continue

            out_path = _output_path_for(f_in, args.output)
            if any(os.path.realpath(out_path) == os.path.realpath(source)
                   or (os.path.exists(out_path) and os.path.exists(source)
                       and os.path.samefile(out_path, source))
                   for source in args.inputFiles):
                raise ValueError(f'output file would overwrite the input file [{out_path}]')
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f_out:
                f_out.write(html)
        except (LHTMLError, OSError, UnicodeError, ValueError) as e:
            print(f'lhtml: error in {f_in}: {e}', file=sys.stderr)
            errors += 1

    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
