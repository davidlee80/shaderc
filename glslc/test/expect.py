# Copyright 2015 The Shaderc Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A number of common glslc result checks coded in mixin classes.

A test case can use these checks by declaring their enclosing mixin classes
as superclass and providing the expected_* variables required by the check_*()
methods in the mixin classes.
"""
import os.path
from glslc_test_framework import GlslCTest

def convert_to_unix_line_endings(source):
    """Converts all line endings in source to be unix line endings."""
    return source.replace('\r\n', '\n').replace('\r', '\n')

def substitute_file_extension(filename, extension):
    """Substitutes file extension, respecting known shader extensions.

    foo.vert -> foo.vert.[extension] [similarly for .frag, .comp, etc.]
    foo.glsl -> foo.[extension]
    foo.unknown -> foo.[extension]
    foo -> foo.[extension]
    """
    if filename[-5:] not in ['.vert', '.frag', '.tesc', '.tese',
                             '.geom', '.comp']:
        return filename.rsplit('.', 1)[0] + '.' + extension
    else:
        return filename + '.' + extension


def get_object_filename(source_filename):
    """Gets the object filename for the given source file."""
    return substitute_file_extension(source_filename, 'spv')


def get_assembly_filename(source_filename):
    """Gets the assembly filename for the given source file."""
    return substitute_file_extension(source_filename, 's')


def verify_file_non_empty(filename):
    """Checks that a given file exists and is not empty."""
    if not os.path.isfile(filename):
        return False, 'Cannot find file: ' + filename
    if not os.path.getsize(filename):
        return False, 'Empty file: ' + filename
    return True, ''


class ReturnCodeIsZero(GlslCTest):
    """Mixin class for checking that the return code is zero."""

    def check_return_code_is_zero(self, status):
        if status.returncode:
            return False, 'Non-zero return code: {ret}\n'.format(
                ret=status.returncode)
        return True, ''


class NoOutputOnStdout(GlslCTest):
    """Mixin class for checking that there is no output on stdout."""

    def check_no_output_on_stdout(self, status):
        if status.stdout:
            return False, 'Non empty stdout: {out}\n'.format(out=status.stdout)
        return True, ''


class NoOutputOnStderr(GlslCTest):
    """Mixin class for checking that there is no output on stderr."""

    def check_no_output_on_stderr(self, status):
        if status.stderr:
            return False, 'Non empty stderr: {err}\n'.format(err=status.stderr)
        return True, ''


class SuccessfulReturn(ReturnCodeIsZero, NoOutputOnStdout, NoOutputOnStderr):
    """Mixin class for checking that return code is zero and no output on
    stdout and stderr."""
    pass


class CorrectObjectFilePreamble(GlslCTest):
    """Provides methods for verifying preamble for a SPV object file."""

    def verify_object_file_preamble(self, filename):
        """Checks that the given SPIR-V binary file has correct preamble."""

        def read_word(binary, index, little_endian):
            """Reads the index-th word from the given binary file."""
            word = binary[index * 4:(index + 1) * 4]
            if little_endian:
                word = reversed(word)
            return reduce(lambda w, b: (w << 8) | ord(b), word, 0)

        def check_endianness(binary):
            """Checks the endianness of the given SPIR-V binary file.

            Returns:
              True if it's little endian, False if it's big endian.
              None if magic number is wrong.
            """
            first_word = read_word(binary, 0, True)
            if first_word == 0x07230203:
                return True
            first_word = read_word(binary, 0, False)
            if first_word == 0x07230203:
                return False
            return None

        success, message = verify_file_non_empty(filename)
        if not success:
            return False, message

        with open(filename, 'rb') as object_file:
            object_file.seek(0, os.SEEK_END)
            num_bytes = object_file.tell()
            if num_bytes % 4 != 0:
                return False, ('Incorrect SPV binary: size should be a multiple'
                               ' of words')
            if num_bytes < 20:
                return False, 'Incorrect SPV binary: size less than 5 words'

            object_file.seek(0)
            preamble = bytes(object_file.read(20))

            little_endian = check_endianness(preamble)
            # SPIR-V module magic number
            if little_endian is None:
                return False, 'Incorrect SPV binary: wrong magic number'

            # SPIR-V version number
            if read_word(preamble, 1, little_endian) != 99:
                return False, 'Incorrect SPV binary: wrong version number'
            # glslang SPIR-V magic number
            if read_word(preamble, 2, little_endian) != 0x051a00bb:
                return False, ('Incorrect SPV binary: wrong generator magic '
                               'number')
            # reserved for instruction schema
            if read_word(preamble, 4, little_endian) != 0:
                return False, 'Incorrect SPV binary: the 5th byte should be 0'

        return True, ''


class CorrectAssemblyFilePreamble(GlslCTest):
    """Provides methods for verifying preamble for a SPV assembly file."""

    def verify_assembly_file_preamble(self, filename):
        success, message = verify_file_non_empty(filename)
        if not success:
            return False, message

        with open(filename) as assembly_file:
            first_line = assembly_file.readline()
            second_line = assembly_file.readline()

        if (first_line != '// Module Version 99\n' or
            second_line != '// Generated by (magic number): 51a00bb\n'):
            return False, 'Incorrect SPV assembly'

        return True, ''


class ValidObjectFile(SuccessfulReturn, CorrectObjectFilePreamble):
    """Mixin class for checking that every input file generates a valid object
    file following the object file naming rule, and there is no output on
    stdout/stderr."""

    def check_object_file_preamble(self, status):
        for input_filename in status.input_filenames:
            object_filename = get_object_filename(input_filename)
            success, message = self.verify_object_file_preamble(
                os.path.join(status.directory, object_filename))
            if not success:
                return False, message
        return True, ''

class ValidFileContents(GlslCTest):
  """Mixin class to test that a specific file contains specific text
  To mix in this class, subclasses need to provide expected_file_contents as
  the contents of the file and target_filename to determine the location."""

  def check_file(self, status):
      target_filename = os.path.join(status.directory, self.target_filename)
      if not os.path.isfile(target_filename):
          return False, 'Cannot find file: ' + target_filename
      with open(target_filename, 'r') as target_file:
          file_contents = target_file.read()
          if file_contents == self.expected_file_contents:
            return True, ''
          return False, ('Incorrect file output: \n{act}\nExpected:\n{exp}'
                         ''.format(act=file_contents,
                                   exp=self.expected_file_contents))
      return False, ('Could not open target file ' + target_filename +
                     ' for reading')


class ValidAssemblyFile(SuccessfulReturn, CorrectAssemblyFilePreamble):
    """Mixin class for checking that every input file generates a valid assembly
    file following the assembly file naming rule, and there is no output on
    stdout/stderr."""

    def check_assembly_file_preamble(self, status):
        for input_filename in status.input_filenames:
            assembly_filename = get_assembly_filename(input_filename)
            success, message = self.verify_assembly_file_preamble(
                os.path.join(status.directory, assembly_filename))
            if not success:
                return False, message
        return True, ''


class ErrorMessage(GlslCTest):
    """Mixin class for tests that fail with a specific error message.

    To mix in this class, subclasses need to provide expected_error as the
    expected error message.
    """

    def check_has_error_message(self, status):
        if not status.returncode:
            return False, ('Expected error message, but returned success from '
                           'glslc')
        if not status.stderr:
            return False, 'Expected error message, but no output on stderr'
        if self.expected_error != convert_to_unix_line_endings(status.stderr):
            return False, ('Incorrect stderr output:\n{act}\n'
                           'Expected:\n{exp}'.format(
                               act=status.stderr, exp=self.expected_error))
        return True, ''


class WarningMessage(GlslCTest):
    """Mixin class for tests that succeed but have a specific warning message.

    To mix in this class, subclasses need to provide expected_warning as the
    expected warning message.
    """

    def check_has_warning_message(self, status):
        if status.returncode:
            return False, ('Expected warning message, but returned failure from'
                           ' glslc')
        if not status.stderr:
            return False, 'Expected warning message, but no output on stderr'
        if self.expected_warning != convert_to_unix_line_endings(status.stderr):
            return False, ('Incorrect stderr output:\n{act}\n'
                           'Expected:\n{exp}'.format(
                               act=status.stderr, exp=self.expected_warning))
        return True, ''


class ValidObjectFileWithWarning(
    NoOutputOnStdout, CorrectObjectFilePreamble, WarningMessage):
    """Mixin class for checking that every input file generates a valid object
    file following the object file naming rule, with a specific warning message.
    """

    def check_object_file_preamble(self, status):
        for input_filename in status.input_filenames:
            object_filename = get_object_filename(input_filename)
            success, message = self.verify_object_file_preamble(
                os.path.join(status.directory, object_filename))
            if not success:
                return False, message
        return True, ''


class ValidAssemblyFileWithWarning(
    NoOutputOnStdout, CorrectAssemblyFilePreamble, WarningMessage):
    """Mixin class for checking that every input file generates a valid assembly
    file following the assembly file naming rule, with a specific warning
    message."""

    def check_assembly_file_preamble(self, status):
        for input_filename in status.input_filenames:
            assembly_filename = get_assembly_filename(input_filename)
            success, message = self.verify_assembly_file_preamble(
                os.path.join(status.directory, assembly_filename))
            if not success:
                return False, message
        return True, ''


class StdoutMatch(GlslCTest):
    """Mixin class for tests that can expect output on stdout.

    To mix in this class, subclasses need to provide expected_stdout as the
    expected stdout output.

    For expected_stdout, if it's True, then they expect something on stdout,
    but will not check what it is. If it's a string, expect an exact match.
    """

    def check_stdout_match(self, status):
        # "True" in this case means we expect something on stdout, but we do not
        # care what it is, we want to distinguish this from "blah" which means we
        # expect exactly the string "blah".
        if self.expected_stdout is True:
            if not status.stdout:
                return False, 'Expected something on stdout'
        else:
            if self.expected_stdout != convert_to_unix_line_endings(status.stdout):
                return False, ('Incorrect stdout output:\n{ac}\n'
                               'Expected:\n{ex}'.format(
                                   ac=status.stdout, ex=self.expected_stdout))
        return True, ''


class StderrMatch(GlslCTest):
    """Mixin class for tests that can expect output on stderr.

    To mix in this class, subclasses need to provide expected_stderr as the
    expected stderr output.

    For expected_stderr, if it's True, then they expect something on stderr,
    but will not check what it is. If it's a string, expect an exact match.
    """

    def check_stderr_match(self, status):
        # "True" in this case means we expect something on stderr, but we do not
        # care what it is, we want to distinguish this from "blah" which means we
        # expect exactly the string "blah".
        if self.expected_stderr is True:
            if not status.stderr:
                return False, 'Expected something on stderr'
        else:
            if self.expected_stderr != convert_to_unix_line_endings(status.stderr):
                return False, ('Incorrect stderr output:\n{ac}\n'
                               'Expected:\n{ex}'.format(
                                   ac=status.stderr, ex=self.expected_stderr))
        return True, ''


class StdoutNoWiderThan80Columns(GlslCTest):
    """Mixin class for tests that require stdout to 80 characters or narrower.

    To mix in this class, subclasses need to provide expected_stdout as the
    expected stdout output.
    """

    def check_stdout_not_too_wide(self, status):
        if not status.stdout:
            return True, ''
        else:
            for line in status.stdout.splitlines():
                if len(line) > 80:
                    return False, ('Stdout line longer than 80 columns: %s'
                                   % line)
        return True, ''
