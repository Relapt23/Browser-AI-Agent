import argparse
import asyncio

from browser_agent.agent import Agent
from browser_agent.config import BrowserSettings, LLMSettings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser AI Agent")
    parser.add_argument("task", nargs="?", help="Задача для выполнения")
    parser.add_argument("--headless", action="store_true", help="Запуск без GUI")
    parser.add_argument("--max-steps", type=int, help="Максимальное кол-во шагов")
    parser.add_argument("--model", type=str, help="Модель LLM")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    overrides = {}
    if args.headless:
        overrides["HEADLESS"] = True
    if args.max_steps:
        overrides["MAX_STEPS"] = args.max_steps

    task = args.task or input("Введите задачу: ")
    if not task.strip():
        print("Задача не указана")
        return

    browser_settings = BrowserSettings(**overrides)
    llm_settings = LLMSettings(**({"MODEL": args.model} if args.model else {}))

    agent = Agent(browser_settings, llm_settings)
    asyncio.run(agent.run(task))


if __name__ == "__main__":
    main()