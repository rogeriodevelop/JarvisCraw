"""Map Gemini function calls to claude -p invocations."""

from typing import AsyncGenerator

from agent_runner import AgentRunner


class FunctionRouter:
    def __init__(self, agent: AgentRunner):
        self.agent = agent

    async def route(self, name: str, args: dict) -> AsyncGenerator[dict, None]:
        """Route a function call to the appropriate claude -p invocation."""

        if name == "code_task":
            async for event in self.agent.run(
                instruction=args.get("instruction", ""),
                mode="edit",
            ):
                yield event

        elif name == "investigate_and_advise":
            question = args.get("question", "")
            async for event in self.agent.run(
                instruction=(
                    f"The developer is asking: {question}. "
                    "Read the relevant code and give your grounded "
                    "recommendation with tradeoffs."
                ),
                mode="edit",
                allowed_tools="Read,Glob,Grep,LS,Search",
            ):
                yield event

        elif name == "read_file":
            path = args.get("path", "")
            async for event in self.agent.run(
                instruction=f"Read the file at {path} and provide a concise summary of its contents.",
                mode="edit",
                allowed_tools="Read",
            ):
                yield event

        elif name == "run_command":
            command = args.get("command", "")
            async for event in self.agent.run(
                instruction=f"Run this shell command and report the output: {command}",
                mode="edit",
            ):
                yield event

        elif name == "get_status":
            async for event in self.agent.run(
                instruction=(
                    "What files have been modified in this session? "
                    "Show a brief summary of recent changes."
                ),
                mode="edit",
                allowed_tools="Read,Glob,Grep,LS,Search",
            ):
                yield event

        elif name == "plan_task":
            instruction = args.get("instruction", "")
            async for event in self.agent.run(
                instruction=(
                    f"Analyze and create a detailed plan for: {instruction}. "
                    "Do NOT make any changes. Only read code, analyze, and produce a step-by-step plan."
                ),
                mode="edit",
                allowed_tools="Read,Glob,Grep,LS,Bash,Search",
            ):
                yield event

        elif name == "debug_issue":
            description = args.get("description", "")
            async for event in self.agent.run(
                instruction=(
                    f"Debug this issue: {description}. "
                    "Investigate the codebase, identify the root cause, "
                    "and suggest a fix with specific code changes. "
                    "Do NOT apply fixes yet — only diagnose and recommend."
                ),
                mode="edit",
                allowed_tools="Read,Glob,Grep,LS,Bash,Search",
            ):
                yield event

        elif name == "review_changes":
            scope = args.get("scope", "recent")
            async for event in self.agent.run(
                instruction=(
                    f"Review {scope} code changes. Run git diff or git log as needed. "
                    "Check for bugs, security issues, code quality problems, and suggest improvements. "
                    "Be concise and actionable."
                ),
                mode="edit",
                allowed_tools="Read,Glob,Grep,LS,Bash,Search",
            ):
                yield event

        elif name == "computer_control":
            # Pass all arguments to the agent
            async for event in self.agent.run(
                instruction=f"Execute desktop action with these parameters: {args}. You can use 'launch_app' for reliable application opening and 'manage_background_task' for status monitoring every few seconds.",
                mode="edit",
                allowed_tools="computer_control,Bash,Read,Glob,launch_app,manage_background_task",
            ):
                yield event

        elif name == "launch_app":
            app_name = args.get("name", "")
            async for event in self.agent.run(
                instruction=f"Abra o aplicativo: {app_name}",
                mode="edit",
                allowed_tools="launch_app",
            ):
                yield event

        elif name == "manage_background_task":
            action = args.get("action", "")
            instr = args.get("instruction", "")
            async for event in self.agent.run(
                instruction=f"Gerencie tarefa em background: {action} - {instr}",
                mode="edit",
                allowed_tools="manage_background_task",
            ):
                yield event

        else:
            yield {
                "type": "function_result",
                "result": f"Unknown function: {name}",
                "is_error": True,
            }
