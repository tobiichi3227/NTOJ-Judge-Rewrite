from dataclasses import dataclass
import os
import glob

from models import CompilationTarget, Challenge, SandboxStatus, Status, MessageType, Compiler
from problem.mixins import UserProgramMixin, CheckerMixin, ManagerMixin
from lang.base import langs
from sandbox.sandbox import SandboxResult
from utils import logger

@dataclass(slots=True)
class UserProgramCompilationTarget(CompilationTarget):
    context: 'UserProgramMixin'

    def can_compile(self, chal: 'Challenge') -> bool:
        if self.context.has_grader:
            lang = langs[self.context.userprog_compiler]
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            if not os.path.exists(grader_folder_path):
                logger.error(f"Grader folder not found for {lang.name} for chal {chal.chal_id}")
                chal.result.total_result.status = Status.JudgeError
                chal.result.total_result.ie_message = f"{lang.name} version grader not support, please contact administrator or problem setter."
                chal.result.total_result.message_type = MessageType.TEXT
                return False

            if self.context.userprog_compiler == Compiler.python3:
                grader_filename = f"{self.context.grader_name}.py"
                grader_path = os.path.join(grader_folder_path, grader_filename)
                if not os.path.exists(grader_path):
                    logger.error(f"{grader_filename} not found for Python3 grader in chal {chal.chal_id}")
                    chal.result.total_result.status = Status.JudgeError
                    chal.result.total_result.ie_message = f"Python3 version grader need {grader_filename}, but file not found.\n please contact administrator or problem setter."
                    chal.result.total_result.message_type = MessageType.TEXT
                    return False
            elif self.context.userprog_compiler == Compiler.java:
                grader_filename = f"{self.context.grader_name}.java"
                grader_path = os.path.join(grader_folder_path, grader_filename)
                if not os.path.exists(grader_path):
                    logger.error(f"{grader_filename} not found for Java grader in chal {chal.chal_id}")
                    chal.result.total_result.status = Status.JudgeError
                    chal.result.total_result.ie_message = f"Java version grader need {grader_filename}, but file not found.\n please contact administrator or problem setter."
                    chal.result.total_result.message_type = MessageType.TEXT
                    return False

        return True

    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        lang = langs[self.context.userprog_compiler]
        copy_in = (
            list(chal.code_paths)
            if chal.code_paths
            else [(chal.code_path, f"a{lang.source_ext}")]
        )

        if self.context.has_grader:
            grader_folder_path = os.path.join(chal.res_path, "grader", lang.name)
            for name in os.listdir(grader_folder_path):
                if os.path.isdir(os.path.join(grader_folder_path, name)):
                    continue

                copy_in.append((os.path.join(grader_folder_path, name), name))
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        lang = langs[self.context.userprog_compiler]
        sources = (
            [name for _, name in chal.code_paths]
            if chal.code_paths
            else [f"a{lang.source_ext}"]
        )
        if self.context.has_grader:
            if self.context.userprog_compiler in (
                Compiler.clang_c_11,
                Compiler.clang_cpp_17,
                Compiler.gcc_c_11,
                Compiler.gcc_cpp_17,
                Compiler.asm_with_libc,
                Compiler.asm_with_libstdcpp,
            ):
                for sourcefile in glob.glob(
                    f"{chal.res_path}/grader/{lang.name}/*{lang.source_ext}"
                ):
                    sources.append(os.path.basename(sourcefile))

            elif self.context.userprog_compiler == Compiler.python3:
                sources.append(f"{self.context.grader_name}.py")
                sources.reverse()
            elif self.context.userprog_compiler == Compiler.java:
                sources.append(f"{self.context.grader_name}.java")
                sources.reverse()

            elif self.context.userprog_compiler == Compiler.rust:
                sources = [f"{self.context.grader_name}.rs"]

        return sources

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        return self.context.userprog_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return self.context.userprog_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        return f"a{langs[self.context.userprog_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file: str):
        logger.info(f"User program compilation succeeded for chal {chal.chal_id}")
        self.context.userprog_path = chal.box.get_file(file)

    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        logger.info(f"User program compilation failed for chal {chal.chal_id}, status: {res.status}")
        stderr_name = f"{self.get_output_name(chal)}-stderr"
        stderr = chal.box.get_file(stderr_name)
        if stderr:
            with open(stderr) as f:
                chal.result.total_result.ce_message = f.read()
            chal.box.delete_file(stderr_name)

        chal.result.total_result.message_type = MessageType.TEXT
        if res.status in (SandboxStatus.NonzeroExitStatus, SandboxStatus.Signalled):
            chal.result.total_result.status = Status.CompileError
            logger.info(f"Compile error for chal {chal.chal_id}")

        elif res.status in (
            SandboxStatus.TimeLimitExceeded,
            SandboxStatus.MemoryLimitExceeded,
            SandboxStatus.OutputLimitExceeded,
        ):
            chal.result.total_result.status = Status.CompileLimitExceeded
            logger.info(f"Compile limit exceeded for chal {chal.chal_id}, limit type: {res.status}")
        elif res.status == SandboxStatus.RunnerError:
            chal.result.total_result.status = Status.InternalError
            logger.error(f"Internal error during compilation for chal {chal.chal_id}")

@dataclass(slots=True)
class CheckerCompilationTarget(CompilationTarget):
    context: 'CheckerMixin'
    def can_compile(self, chal: 'Challenge') -> bool:
        assert self.context.checker_compiler
        lang = langs[self.context.checker_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        if not os.path.exists(os.path.join(checker_path, checker_name)):
            logger.error(f"Checker file {checker_name} not found in chal {chal.chal_id}")
            chal.result.total_result.status = Status.JudgeError
            chal.result.total_result.ie_message = f"{checker_name} not found, please contact administrator or problem setter"
            chal.result.total_result.message_type = MessageType.TEXT
            return False
        return True

    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        assert self.context.checker_compiler
        lang = langs[self.context.checker_compiler]
        checker_name = f"checker{lang.source_ext}"
        checker_path = os.path.join(chal.res_path, "checker")
        copy_in = [(os.path.join(checker_path, checker_name), checker_name)]

        for name in os.listdir(checker_path):
            if os.path.isdir(name):
                continue

            copy_in.append((os.path.join(checker_path, name), name))
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        assert self.context.checker_compiler
        return [f"checker{langs[self.context.checker_compiler].source_ext}"]

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        assert self.context.checker_compiler
        return self.context.checker_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return self.context.checker_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        assert self.context.checker_compiler
        return f"checker{langs[self.context.checker_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file: str):
        logger.info(f"Checker compilation succeeded for chal {chal.chal_id}")
        self.context.checker_path = chal.box.get_file(file)

    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        logger.error(f"Checker compilation failed for chal {chal.chal_id}, status: {res.status}")
        chal.result.total_result.status = Status.JudgeError
        chal.result.total_result.message_type = MessageType.TEXT
        stderr_name = f"{self.get_output_name(chal)}-stderr"
        stderr = chal.box.get_file(stderr_name)
        if stderr:
            with open(stderr) as f:
                chal.result.total_result.ce_message = f.read()
            chal.box.delete_file(stderr_name)


@dataclass(slots=True)
class ManagerCompilationTarget(CompilationTarget):
    context: 'ManagerMixin'

    def can_compile(self, chal: 'Challenge') -> bool:
        lang = langs[self.context.manager_compiler]
        manager_name = f"manager{lang.source_ext}"
        manager_path = os.path.join(chal.res_path, "grader", manager_name)
        if os.path.isfile(manager_path):
            return True

        logger.error(f"Manager file {manager_name} not found in chal {chal.chal_id}")
        chal.result.total_result.status = Status.JudgeError
        chal.result.total_result.ie_message = (
            f"{manager_name} not found, please contact administrator or problem setter"
        )
        chal.result.total_result.message_type = MessageType.TEXT
        return False

    def get_source_files(self, chal: 'Challenge') -> list[tuple[str, str]]:
        lang = langs[self.context.manager_compiler]
        manager_name = f"manager{lang.source_ext}"
        grader_path = os.path.join(chal.res_path, "grader")
        copy_in = [(os.path.join(grader_path, manager_name), manager_name)]

        for name in os.listdir(grader_path):
            path = os.path.join(grader_path, name)
            if name == manager_name or os.path.isdir(path):
                continue
            copy_in.append((path, name))
        return copy_in

    def get_source_list(self, chal: 'Challenge') -> list[str]:
        lang = langs[self.context.manager_compiler]
        return [f"manager{lang.source_ext}"]

    def get_compiler(self, chal: 'Challenge') -> 'Compiler':
        return self.context.manager_compiler

    def get_compile_args(self, chal: 'Challenge') -> list[str]:
        return self.context.manager_compile_args

    def get_output_name(self, chal: 'Challenge') -> str:
        return f"manager{langs[self.context.manager_compiler].executable_ext}"

    def on_compile_success(self, chal: 'Challenge', file: str):
        logger.info(f"Manager compilation succeeded for chal {chal.chal_id}")
        self.context.manager_path = chal.box.get_file(file)

    def on_compile_failure(self, chal: 'Challenge', res: SandboxResult):
        logger.error(
            f"Manager compilation failed for chal {chal.chal_id}, status: {res.status}"
        )
        chal.result.total_result.status = Status.JudgeError
        chal.result.total_result.message_type = MessageType.TEXT
        stderr_name = f"{self.get_output_name(chal)}-stderr"
        stderr = chal.box.get_file(stderr_name)
        if stderr:
            with open(stderr) as f:
                chal.result.total_result.ce_message = f.read()
            chal.box.delete_file(stderr_name)
