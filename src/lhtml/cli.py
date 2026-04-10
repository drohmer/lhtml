"""LHTML command-line interface.

Usage:
    lhtml [-w] inputFile [-o outputFile]
    python -m lhtml [-w] inputFile [-o outputFile]
"""

import os
import argparse

from .pipeline import ProcessingPipeline


_pipeline = ProcessingPipeline()


def _ensure_trailing_newline(text):
    if text and text[-1] != '\n':
        return text + '\n'
    return text


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Lightweight HTML')
    parser.add_argument('inputFile', help='Input filepath')
    parser.add_argument('-w', '--wrapAuto',
                        help='Wrap content in basic HTML template',
                        action='store_true')
    parser.add_argument('-o', '--outputFile', help='Output filepath')
    args = parser.parse_args()

    meta = {}
    if args.wrapAuto:
        meta['wrap-auto'] = True

    meta['directory_include'] = [os.getcwd() + '/']
    f_in = args.inputFile

    if os.path.isfile(f_in):
        dir_to_include = os.path.dirname(f_in)
        if dir_to_include:
            meta['directory_include'].append(
                os.path.join(os.getcwd(), dir_to_include) + '/'
            )

        with open(f_in) as fid:
            txt = _ensure_trailing_newline(fid.read())

        html = _ensure_trailing_newline(_pipeline.run(txt, meta))

        if args.outputFile:
            with open(args.outputFile, 'w') as f_out:
                f_out.write(html)
        else:
            print(html)
    else:
        print(f'Error: unrecognized input file [{f_in}]')


if __name__ == '__main__':
    main()
