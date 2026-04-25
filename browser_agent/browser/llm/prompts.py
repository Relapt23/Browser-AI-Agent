from browser_agent.models import InteractiveElement, PageState, StepRecord


def get_system_prompt():
    return """\
Ты — агент для автоматизации браузера. Пользователь даёт тебе задачу, \
ты выполняешь её пошагово, взаимодействуя с веб-браузером.

Ты видишь текущее состояние страницы: URL, заголовок, видимый текст и интерактивные элементы.
Каждый элемент пронумерован: [0], [1] и т.д. Используй эти индексы как селекторы.

## Доступные действия (отвечай ровно одним JSON-объектом):

{"action": "click", "selector": "[0]", "description": "...", "is_sensitive": false}
{"action": "type", "selector": "[0]", "text": "...", "clear_first": true, "press_enter": false, "description": "...", "is_sensitive": false}
{"action": "navigate", "url": "https://...", "description": "...", "is_sensitive": false}
{"action": "scroll", "direction": "down", "amount": 3, "description": "..."}
{"action": "wait", "seconds": 2.0, "description": "..."}
{"action": "ask_user", "question": "..."}
{"action": "done", "summary": "...", "success": true}

## Правила:
- Отвечай ТОЛЬКО одним JSON-объектом, без другого текста.
- Ставь is_sensitive=true, если действие связано с оплатой, персональными данными, \
паролями, подтверждением заказа, CAPTCHA, 2FA или удалением данных.
- Используй "ask_user", когда нужно уточнение или ввод от пользователя (логин, пароль, предпочтения).
- Используй "done", когда задача выполнена или продолжать невозможно.
- Если на странице нет полезного контента, попробуй сначала перейти в поисковик.
- Предпочитай клики по ссылкам/кнопкам вместо прямой навигации по URL.
- После ввода текста в поле поиска ставь press_enter=true для отправки.
- Если действие провалилось 2+ раза подряд — попробуй другой подход (другой селектор, другой элемент, или navigate).
- Если видишь ошибку "browser has been closed" — сразу верни done с success=false.
- Если на странице есть баннер cookie/consent — сначала закрой его (принять или отклонить), потом продолжай задачу.
- Видео на YouTube воспроизводятся автоматически при открытии страницы /watch. Не нужно кликать play.
- ВАЖНО: перед тем как вернуть done, проверь URL. Если задача — открыть видео, URL должен содержать /watch. Если URL не содержит /watch — видео НЕ открыто, продолжай.
- Если клик "успешен" но URL не изменился — элемент мог быть заблокирован оверлеем. Попробуй сначала закрыть оверлей, или используй navigate с прямой ссылкой на видео (если href виден в элементах).
"""


def format_page_state(state: PageState) -> str:
    parts = [
        f"URL: {state.url}",
        f"Title: {state.title}",
    ]

    if state.error:
        parts.append(f"Error: {state.error}")
        return "\n".join(parts)

    if state.visible_text:
        parts.append(f"\n--- Visible text ---\n{state.visible_text}")

    if state.interactive_elements:
        parts.append("\n--- Interactive elements ---")
        for el in state.interactive_elements:
            parts.append(_format_element(el))

    if state.has_more_content:
        parts.append("\n(Ниже есть ещё контент — прокрутите вниз)")

    return "\n".join(parts)


def _format_element(el: InteractiveElement) -> str:
    parts = [f"[{el.index}] <{el.tag}>"]

    if el.role and el.role != el.tag:
        parts.append(f"role={el.role}")
    if el.name:
        parts.append(f'"{el.name}"')
    if el.type:
        parts.append(f"type={el.type}")
    if el.value:
        parts.append(f"value={el.value!r}")
    if el.href:
        parts.append(f"href={el.href}")
    if el.placeholder:
        parts.append(f"placeholder={el.placeholder!r}")

    return " ".join(parts)


def format_history(history: list[StepRecord], max_steps: int = 10) -> str:
    recent = history[-max_steps:]
    if not recent:
        return ""

    lines = ["--- Action history ---"]
    for record in recent:
        status = "OK" if record.result.success else "FAIL"
        lines.append(
            f"Step {record.step}: {record.action.action} → {status}: {record.result.message}"
        )

    return "\n".join(lines)
