from __future__ import unicode_literals

import subprocess

from . import ConverterBase
from ..exceptions import ConvertError, IdentifyError, UnknownFileFormat
from ..literals import (
    TRANSFORMATION_RESIZE, TRANSFORMATION_ROTATE, TRANSFORMATION_ZOOM
)
from ..literals import (
    DEFAULT_FILE_FORMAT, DEFAULT_PAGE_NUMBER, DIMENSION_SEPARATOR
)
from ..settings import GM_PATH, GM_SETTINGS

CONVERTER_ERROR_STARTS_WITH = 'starts with'
CONVERTER_ERROR_STRING_NO_DECODER = 'No decode delegate for this image format'


class GraphicsMagick(ConverterBase):
    def identify_file(self, input_filepath, arguments=None):
        command = []
        command.append(unicode(GM_PATH))
        command.append('identify')
        if arguments:
            command.extend(arguments)
        command.append(unicode(input_filepath))
        proc = subprocess.Popen(command, close_fds=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        return_code = proc.wait()
        if return_code != 0:
            raise IdentifyError(proc.stderr.readline())
        return proc.stdout.read()

    def convert_file(self, input_filepath, output_filepath, transformations=None, page=DEFAULT_PAGE_NUMBER, file_format=DEFAULT_FILE_FORMAT, **kwargs):
        arguments = []

        try:
            if transformations:
                for transformation in transformations:
                    if transformation['transformation'] == TRANSFORMATION_RESIZE:
                        dimensions = []
                        dimensions.append(unicode(transformation['arguments']['width']))
                        if 'height' in transformation['arguments']:
                            dimensions.append(unicode(transformation['arguments']['height']))
                        arguments.append('-resize')
                        arguments.append('%s' % DIMENSION_SEPARATOR.join(dimensions))

                    elif transformation['transformation'] == TRANSFORMATION_ZOOM:
                        arguments.append('-resize')
                        arguments.append('%d%%' % transformation['arguments']['percent'])

                    elif transformation['transformation'] == TRANSFORMATION_ROTATE:
                        arguments.append('-rotate')
                        arguments.append('%s' % transformation['arguments']['degrees'])
        except:
            pass

        if file_format.lower() == 'jpeg' or file_format.lower() == 'jpg':
            arguments.append('-quality')
            arguments.append('85')

        # Graphicsmagick page number is 0 base
        input_arg = '%s[%d]' % (input_filepath, page - 1)

        # Specify the file format next to the output filename
        output_filepath = '%s:%s' % (file_format, output_filepath)

        command = []
        command.append(unicode(GM_PATH))
        command.append('convert')
        command.extend(unicode(GM_SETTINGS).split())
        command.append(unicode(input_arg))
        if arguments:
            command.extend(arguments)
        command.append(unicode(output_filepath))
        proc = subprocess.Popen(command, close_fds=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        return_code = proc.wait()
        if return_code != 0:
            # Got an error from convert program
            error_line = proc.stderr.readline()
            if (CONVERTER_ERROR_STRING_NO_DECODER in error_line) or (CONVERTER_ERROR_STARTS_WITH in error_line):
                # Try to determine from error message which class of error is it
                raise UnknownFileFormat
            else:
                raise ConvertError(error_line)

    def get_available_transformations(self):
        return [
            TRANSFORMATION_RESIZE, TRANSFORMATION_ROTATE,
            TRANSFORMATION_ZOOM
        ]

    def get_page_count(self, input_filepath):
        try:
            return len(self.identify_file(unicode(input_filepath)).splitlines())
        except IdentifyError:
            raise UnknownFileFormat
