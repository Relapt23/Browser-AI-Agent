from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from browser_agent.models import AgentAction, ActionResult

console = Console()


def show_task_start(task: str) -> None:
    console.print()
    console.print(Panel(task, title="Task", border_style="cyan"))
    console.print()


def show_step(step: int, max_steps: int, action: AgentAction, url: str) -> None:
    label = f"[bold][Step {step}/{max_steps}][/bold]"
    action_type = action.action.upper()
    desc = getattr(action, "description", None) or getattr(action, "question", None) or ""
    console.print(f"\n{label} [yellow]{action_type}[/yellow]: {desc}")
    console.print(f"  [dim]URL: {url}[/dim]")


def show_result(result: ActionResult) -> None:
    if result.success:
        console.print(f"  [green]✓[/green] {result.message}")
    else:
        console.print(f"  [red]✗[/red] {result.message}")
        if result.error:
            console.print(f"    [dim red]{result.error}[/dim red]")


def show_done(summary: str, success: bool) -> None:
    style = "green" if success else "red"
    title = "Task Completed" if success else "Task Failed"
    console.print()
    console.print(Panel(summary, title=title, border_style=style))


def show_error(error: str) -> None:
    console.print(f"[bold red]Error:[/bold red] {error}")


def show_warning(message: str) -> None:
    console.print(f"[yellow]⚠ {message}[/yellow]")


def ask_confirmation(reason: str) -> bool:
    return Confirm.ask(f"\n[yellow]⚠ {reason}[/yellow] Continue?", default=False)


def ask_input(question: str) -> str:
    return Prompt.ask(f"\n[cyan]Agent asks:[/cyan] {question}")