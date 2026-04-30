from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from browser_agent.models import AgentAction, ActionResult, AskUser, Click, Done, Type

console = Console()


def show_task_start(task: str) -> None:
    console.print()
    console.print(Panel(task, title="Task", border_style="cyan"))
    console.print()


def show_step(step: int, max_steps: int, action: AgentAction, url: str) -> None:
    label = f"[bold][Step {step}/{max_steps}][/bold]"
    action_type = action.action.upper()

    if isinstance(action, (Click, Type)):
        desc = action.description
    elif isinstance(action, AskUser):
        desc = action.question
    elif isinstance(action, Done):
        desc = action.summary
    else:
        desc = action.description

    console.print(f"\n{label} [yellow]{action_type}[/yellow]: {desc}")
    console.print(f"  [dim]URL: {url}[/dim]")

    if isinstance(action, (Click, Type)):
        console.print(f"  [dim]element={action.element_id} snapshot={action.snapshot_id}[/dim]")


def show_result(result: ActionResult) -> None:
    if result.success:
        console.print(f"  [green]V[/green] {result.message}")
    else:
        console.print(f"  [red]X[/red] {result.message}")
        if result.error:
            console.print(f"    [dim red]{result.error}[/dim red]")

    if result.observation:
        console.print(f"    [dim]{result.observation}[/dim]")

    if result.verification_passed is not None:
        if result.verification_passed:
            console.print(f"    [green]verified[/green]")
        else:
            console.print(f"    [red]verification failed[/red]")


def show_done(summary: str, success: bool) -> None:
    style = "green" if success else "red"
    title = "Task Completed" if success else "Task Failed"
    console.print()
    console.print(Panel(summary, title=title, border_style=style))


def show_warning(message: str) -> None:
    console.print(f"[yellow]! {message}[/yellow]")


def ask_confirmation(reason: str) -> bool:
    return Confirm.ask(f"\n[yellow]! {reason}[/yellow] Continue?", default=False)


def ask_input(question: str) -> str:
    return Prompt.ask(f"\n[cyan]Agent asks:[/cyan] {question}")