from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from urllib.parse import urlsplit

from pywinauto import Desktop
from pywinauto.keyboard import send_keys
from pywinauto.uia_defines import NoPatternInterfaceError

from bybit_automation.models.merchant_cycle import AdvertisementSnapshot, MerchantSearchResult
from bybit_automation.services.logging_service import AppLogger


@dataclass(frozen=True)
class PaymentMethodState:
    bank_transfer: bool
    mobile_top_up: bool
    cash_deposit: bool


class ExistingBrowserWindowDriver:
    ADS_URL = "https://www.bybit.com/ru-RU/p2p/merchant-admin/ads"
    SELL_URL = "https://www.bybit.com/ru-RU/p2p/sell/USDT/RUB"

    def __init__(self, logger: AppLogger | None = None) -> None:
        self._logger = logger

    def _log(self, message: str) -> None:
        if self._logger is not None:
            self._logger.info(message)

    _BYBIT_DOCUMENT_TITLE_PARTS = (
        "bybit p2p crypto trading",
        "криптотрейдинг на bybit p2p",
        "продать usdt за rub",
        "buy crypto with currency",
    )

    def _find_window(self, window_title: str):
        fallback_candidates: list[object] = []
        suffix = self._window_suffix(window_title)
        for window in Desktop(backend="uia").windows():
            try:
                title = window.window_text()
            except Exception:
                continue
            if title == window_title:
                return window
            if suffix and title.endswith(suffix):
                fallback_candidates.append(window)
        if fallback_candidates:
            return fallback_candidates[0]
        raise RuntimeError(f"Окно браузера не найдено: {window_title}")

    def _window_suffix(self, window_title: str) -> str:
        parts = [part.strip() for part in window_title.split(" - ") if part.strip()]
        if len(parts) >= 2:
            return " - ".join(parts[-2:])
        return window_title.strip()

    def _find_main_document(self, window):
        for control in window.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            title_lower = title.lower()
            if control_type == "Document" and any(part in title_lower for part in self._BYBIT_DOCUMENT_TITLE_PARTS):
                return control
        raise RuntimeError("Не удалось найти основной документ страницы Bybit.")

    def _find_first_document(self, window):
        for control in window.descendants():
            try:
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if control_type == "Document":
                return control
        raise RuntimeError("Не удалось найти документ страницы.")

    def _find_document_by_title_part(self, window, title_part: str):
        title_part_lower = title_part.lower()
        for control in window.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if control_type == "Document" and title_part_lower in title.lower():
                return control
        raise RuntimeError(f"Не удалось найти документ страницы с фрагментом '{title_part}'.")

    def _interactive_items(self, root) -> list[object]:
        items: list[object] = []
        for control in root.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if title and control_type in {
                "Button",
                "CheckBox",
                "DataItem",
                "Edit",
                "Group",
                "Hyperlink",
                "ListItem",
                "RadioButton",
                "Text",
            }:
                items.append(control)
        return items

    def _document_contains_any_text(self, root, text_parts: tuple[str, ...]) -> bool:
        needles = tuple(text.lower() for text in text_parts)
        for control in self._interactive_items(root):
            text = self._item_text(control).lower()
            if any(needle in text for needle in needles):
                return True
        return False

    def _item_text(self, control) -> str:
        return control.window_text().strip()

    def _item_type(self, control) -> str:
        return getattr(getattr(control, "element_info", None), "control_type", "")

    def _is_forbidden_click_text(self, text: str) -> bool:
        normalized = self._normalize_merchant_name(text)
        forbidden = (
            "все объявления",
            "купить монеты",
            "продать монеты",
            "начинающий",
            "продвинутый",
            "мейкер",
            "безопасность и предотвращение мошенничества",
            "faq",
        )
        return any(marker == normalized for marker in forbidden)

    def _find_exact(self, root, *, title: str, control_types: tuple[str, ...]):
        for control in self._interactive_items(root):
            if self._item_text(control) == title and self._item_type(control) in control_types:
                return control
        raise RuntimeError(f"Не найден элемент '{title}'.")

    def _find_contains(self, root, *, text_part: str, control_types: tuple[str, ...]):
        needle = text_part.lower()
        for control in self._interactive_items(root):
            if needle in self._item_text(control).lower() and self._item_type(control) in control_types:
                return control
        raise RuntimeError(f"Не найден элемент, содержащий '{text_part}'.")

    def _find_edit_after_label(self, root, label_text: str):
        items = self._interactive_items(root)
        for index, control in enumerate(items):
            if self._item_text(control) != label_text:
                continue
            for next_control in items[index + 1 :]:
                if self._item_type(next_control) == "Edit":
                    return next_control
        raise RuntimeError(f"Не найдено поле после метки '{label_text}'.")

    def _find_input_after_label(self, root, label_text: str):
        items = self._interactive_items(root)
        for index, control in enumerate(items):
            if self._item_text(control) != label_text:
                continue
            for next_control in items[index + 1 :]:
                if self._item_type(next_control) == "Edit":
                    return next_control
                if self._item_text(next_control):
                    break
        raise RuntimeError(f"Не найдено поле после метки '{label_text}'.")

    def _find_group_after_label(self, root, label_text: str):
        items = self._interactive_items(root)
        for index, control in enumerate(items):
            if self._item_text(control) != label_text:
                continue
            for next_control in items[index + 1 :]:
                if self._item_type(next_control) == "Group":
                    return next_control
                if self._item_text(next_control):
                    break
        raise RuntimeError(f"Не найдена группа после метки '{label_text}'.")

    def _safe_toggle_state(self, control) -> int | None:
        try:
            return control.get_toggle_state()
        except Exception:
            try:
                return control.iface_toggle.CurrentToggleState
            except Exception:
                return None

    def _click_best(self, control, *, allow_forbidden_text: bool = False) -> None:
        text = self._item_text(control)
        if not allow_forbidden_text and self._is_forbidden_click_text(text):
            raise RuntimeError(f"Запрещён лишний клик по элементу '{text}'.")
        try:
            control.invoke()
            self._log(f"click_best: invoke succeeded for '{text}'")
            time.sleep(0.2)
            return
        except Exception:
            pass
        try:
            control.iface_invoke.Invoke()
            self._log(f"click_best: iface_invoke succeeded for '{text}'")
            time.sleep(0.2)
            return
        except Exception:
            pass
        try:
            control.select()
            self._log(f"click_best: select succeeded for '{text}'")
            time.sleep(0.2)
            return
        except Exception:
            pass
        try:
            control.iface_selection_item.Select()
            self._log(f"click_best: iface_selection_item succeeded for '{text}'")
            time.sleep(0.2)
            return
        except Exception:
            pass
        control.set_focus()
        self._log(f"click_best: set_focus + send_keys fallback for '{text}'")
        time.sleep(0.2)
        send_keys("{ENTER}")
        time.sleep(0.2)

    def _set_checkbox_state(self, control, checked: bool) -> None:
        state = self._safe_toggle_state(control)
        if state is not None and bool(state) == checked:
            return
        try:
            control.toggle()
            time.sleep(0.2)
        except Exception:
            try:
                control.iface_toggle.Toggle()
                time.sleep(0.2)
            except Exception:
                control.set_focus()
                time.sleep(0.2)
                send_keys(" ")
        time.sleep(0.2)

    def _select_visible_payment_method(self, root, name: str) -> None:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                checkbox = self._find_exact(root, title=name, control_types=("CheckBox",))
                self._set_checkbox_state(checkbox, True)
                return
            except RuntimeError:
                pass

            try:
                label = self._find_exact(root, title=name, control_types=("Text", "ListItem", "Button"))
                target = label.parent() if self._item_type(label) == "Text" else label
                self._click_best(target)
                time.sleep(0.2)
                return
            except RuntimeError:
                time.sleep(0.2)

        raise RuntimeError(f"Не найден элемент {name}")

    def focus(self, window_title: str) -> None:
        window = self._find_window(window_title)
        window.set_focus()
        time.sleep(0.2)

    def _tab_items(self, window) -> list[object]:
        tabs: list[object] = []
        for control in window.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if control_type != "TabItem" or not title:
                continue
            title_lower = title.lower()
            if title_lower in {"system", "minimize", "restore", "close"}:
                continue
            tabs.append(control)
        return tabs

    def _control_value(self, control) -> str:
        try:
            value = control.iface_value.CurrentValue
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
        return self._item_text(control)

    def _read_current_url(self, window) -> str:
        candidates: list[str] = []
        for control in window.descendants():
            try:
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if control_type != "Edit":
                continue
            value = self._control_value(control)
            if "bybit.com/" in value or value.startswith("http"):
                candidates.append(value)
        if not candidates:
            return ""
        return max(candidates, key=len)

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        candidate = url.strip()
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        parts = urlsplit(candidate)
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parts.path.rstrip("/") or "/"
        return f"{netloc}{path.lower()}"

    def _url_matches(self, current_url: str, target_url: str) -> bool:
        return self._normalize_url(current_url) == self._normalize_url(target_url)

    def _open_url_in_new_tab(self, window_title: str, url: str) -> None:
        self.focus(window_title)
        send_keys("^t")
        time.sleep(0.2)
        send_keys("^l")
        time.sleep(0.2)
        send_keys(url, with_spaces=True)
        send_keys("{ENTER}")
        time.sleep(1.0)

    def _activate_or_create_tab(self, window_title: str, target_url: str) -> None:
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if self._url_matches(current_url, target_url):
            return

        for control in self._tab_items(window):
            if self._is_forbidden_click_text(self._item_text(control)):
                self._log(
                    f"_activate_or_create_tab: пропускаю запрещённый TabItem '{self._item_text(control)}'."
                )
                continue
            self._click_best(control, allow_forbidden_text=True)
            time.sleep(0.25)
            if self._url_matches(self._read_current_url(window), target_url):
                return

        try:
            self.open_url(window_title, target_url)
            current_window = self._find_window(window_title)
            current_url = self._read_current_url(current_window)
            if self._url_matches(current_url, target_url):
                return
        except RuntimeError:
            pass

        self._open_url_in_new_tab(window_title, target_url)
        current_window = self._find_window(window_title)
        current_url = self._read_current_url(current_window)
        if not self._url_matches(current_url, target_url):
            raise RuntimeError(f"Не удалось открыть рабочую вкладку {target_url}. Текущий адрес: {current_url or 'не определён'}.")

    def ensure_sell_tab(self, window_title: str) -> None:
        self._activate_or_create_tab(window_title, self.SELL_URL)

    def ensure_ads_tab(self, window_title: str) -> None:
        self._activate_or_create_tab(window_title, self.ADS_URL)

    def refresh_page(self, window_title: str) -> None:
        self.focus(window_title)
        send_keys("{F5}")
        time.sleep(1.0)

    def _normalize_merchant_name(self, text: str) -> str:
        stripped = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE).strip().lower()
        return re.sub(r"\s+", " ", stripped).strip()

    def _is_non_merchant_listing_text(self, normalized_text: str) -> bool:
        excluded_markers = (
            "мерчант",
            "merchant",
            "цена",
            "доступно",
            "лимиты",
            "способ оплаты",
            "cash deposit",
            "mobile top up",
            "bank transfer",
            "быстрая оплата",
            "исполнено",
            "в списке ниже",
            "представлены p2p провайдеры",
            "вашего региона",
            "будьте бдительны",
            "rub",
            "usdt",
        )
        return any(marker in normalized_text for marker in excluded_markers)

    def _is_listing_boundary(self, normalized_text: str) -> bool:
        boundary_markers = (
            "faq",
            "компания",
            "сервисы",
            "поддержка",
            "продукт",
            "начинающий",
            "продвинутый",
            "мейкер",
            "безопасность и предотвращение мошенничества",
            "купить монеты",
            "продать монеты",
            "продайте usdt",
            "купите usdt",
            "в три простых шага",
            "конвертируйте",
        )
        return any(marker in normalized_text for marker in boundary_markers)

    def _extract_merchant_candidates(self, document) -> list[str]:
        candidates: list[str] = []
        seen_header = False
        for control in self._interactive_items(document):
            text = self._item_text(control)
            control_type = self._item_type(control)
            if not text:
                continue
            normalized = self._normalize_merchant_name(text)
            if not seen_header:
                if normalized in {"мерчант", "merchant"}:
                    seen_header = True
                continue
            if self._is_listing_boundary(normalized):
                break
            if not normalized:
                continue
            merchant_name = self._extract_merchant_name(text, control_type)
            if merchant_name is None:
                continue
            candidates.append(merchant_name)
            if len(candidates) >= 10:
                break
        return candidates

    def _extract_merchant_name(self, text: str, control_type: str) -> str | None:
        normalized = self._normalize_merchant_name(text)
        if not normalized:
            return None
        if control_type not in {"Text", "DataItem"}:
            return None
        if control_type == "DataItem":
            if not re.search(r"\s+\d+[\s\xa0]*исполн", text, flags=re.IGNORECASE):
                return None
            merchant_row = re.split(r"\s+\d+[\s\xa0]*исполнено\b", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if not merchant_row:
                return None

            tokens = merchant_row.split()
            while tokens and (len(tokens[0]) == 1 or not re.search(r"[\w\u0400-\u04FF]", tokens[0], flags=re.UNICODE)):
                tokens.pop(0)
            if not tokens:
                return None

            candidate = tokens[0]
        else:
            if self._is_non_merchant_listing_text(normalized):
                return None
            if normalized.isdigit():
                return None
            if re.search(r"\d+,\d{2}", text):
                return None
            candidate = text.strip()

        cleaned = re.sub(r"^[^\w\u0400-\u04FF_]+|[^\w\u0400-\u04FF_]+$", "", candidate, flags=re.UNICODE).strip()
        if len(cleaned) < 2:
            return None
        return cleaned

    def _activate_first_search_page(self, window_title: str) -> None:
        try:
            page_control = self._find_page_control(window_title, 1)
        except RuntimeError:
            return
        self._click_best(page_control)
        time.sleep(0.2)

    def _find_page_control(self, window_title: str, page: int):
        target = str(page)
        document = self._find_main_document(self._find_window(window_title))
        seen_header = False
        clickable_page_types = ("Button", "ListItem", "DataItem", "Hyperlink")
        for control in self._interactive_items(document):
            text = self._item_text(control)
            normalized = self._normalize_merchant_name(text)
            if not seen_header:
                if normalized in {"мерчант", "merchant"}:
                    seen_header = True
                continue
            if self._is_listing_boundary(normalized):
                break
            if text == target and self._item_type(control) in clickable_page_types:
                return control
        raise RuntimeError(f"Не найден элемент '{target}'.")

    def read_current_advertisement(self, window_title: str) -> AdvertisementSnapshot | None:
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.ADS_URL):
            raise RuntimeError(f"Активная вкладка не является Ads-страницей. Определён адрес: {current_url}.")

        document = self._find_main_document(window)
        texts = [self._item_text(control) for control in self._interactive_items(document)]
        side = next((text for text in texts if text.startswith("Покупка") or text.startswith("Продажа")), "")
        advertisement_id = next((text for text in texts if re.fullmatch(r"\d{10,}", text)), "")
        price_text = next((text for text in texts if re.fullmatch(r"\d+,\d{2}\s*RUB", text)), "")
        if not advertisement_id or not price_text:
            return None
        side_value = "Покупка" if side.startswith("Покупка") else "Продажа" if side.startswith("Продажа") else ""
        return AdvertisementSnapshot(
            advertisement_id=advertisement_id,
            price=price_text.replace("RUB", "").strip(),
            side=side_value,
        )

    def delete_current_advertisement(self, window_title: str) -> None:
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.ADS_URL):
            raise RuntimeError(f"Активная вкладка не является Ads-страницей. Определён адрес: {current_url}.")

        snapshot = self.read_current_advertisement(window_title)
        if snapshot is None:
            self._log("delete_current_advertisement: read_current_advertisement вернул None — нет объявления для удаления.")
            return

        ad_id = snapshot.advertisement_id
        self._log(f"delete_current_advertisement: ищу элемент с ID {ad_id}.")

        document = self._find_main_document(window)
        ad_id_control = None
        for control in document.descendants():
            try:
                text = control.window_text().strip()
            except Exception:
                continue
            if text == ad_id:
                ad_id_control = control
                break

        if ad_id_control is None:
            self._log(f"delete_current_advertisement: элемент с ID {ad_id} не найден среди descendants документа.")

            # Диагностика — покажем 50 первых interactive_items в документе
            items = self._interactive_items(document)
            preview = "; ".join(f"[{self._item_type(c)}]{self._item_text(c)[:40]}" for c in items[:50])
            self._log(f"delete_current_advertisement: interactive_items в документе: {preview}")
            raise RuntimeError(f"Не найден элемент с ID объявления {ad_id}.")

        self._log(f"delete_current_advertisement: элемент с ID {ad_id} найден. Ищу Image (иконки действий) в строке.")

        # Берём строку таблицы (level 0 = DataItem row)
        row_data_item = ad_id_control.parent()

        # Собираем все Image из строки
        images_in_row = []
        for child in row_data_item.descendants():
            try:
                ctrl_type = getattr(getattr(child, "element_info", None), "control_type", "")
            except Exception:
                continue
            if ctrl_type == "Image":
                images_in_row.append(child)

        if len(images_in_row) < 3:
            self._log(f"delete_current_advertisement: найдено Image={len(images_in_row)}, нужно минимум 3.")
            raise RuntimeError(f"Не удалось найти кнопку удаления для объявления {ad_id}.")

        # Последние 3 Image — это иконки share, edit, delete
        delete_icon = images_in_row[-1]
        self._log(f"delete_current_advertisement: последний Image в строке, type={self._item_type(delete_icon)}.")

        # Кликаем по самой иконке (SVG) — событие всплывёт до родителя
        self._log("delete_current_advertisement: кликаю по Image (SVG-иконке).")
        delete_icon.click_input()
        time.sleep(1.0)

        # Ждём popup и ищем "Подтвердить"/"Удалить"
        if not self._find_popup_confirm_button(window_title):
            self._log("delete_current_advertisement: popup не найден, пробую Enter (стандартное подтверждение).")
            self.focus(window_title)
            send_keys("{ENTER}")
            time.sleep(0.5)
            # Ещё одна попытка найти popup
            if not self._find_popup_confirm_button(window_title):
                self._log("delete_current_advertisement: Enter не помог, пробую ПКМ по строке.")
                row_data_item.click_input(button='right')
                time.sleep(0.5)
                window = self._find_window(window_title)
                deadline = time.time() + 5
                found_menu_item = False
                while time.time() < deadline:
                    for control in window.descendants():
                        try:
                            text = control.window_text().strip()
                            ctrl_type = getattr(getattr(control, "element_info", None), "control_type", "")
                        except Exception:
                            continue
                        if ctrl_type in ("MenuItem", "Button", "Text") and "Удал" in text:
                            self._log(f"delete_current_advertisement: контекстное меню, кликаю '{text}'.")
                            self._click_best(control, allow_forbidden_text=True)
                            time.sleep(0.3)
                            found_menu_item = True
                            break
                    if found_menu_item:
                        break
                    time.sleep(0.3)
                if found_menu_item:
                    self._find_popup_confirm_button(window_title)

    def _find_popup_confirm_button(self, window_title: str) -> bool:
        """Ищет popup подтверждения удаления и кликает 'Подтвердить'/'Удалить'. Возвращает True если найден."""
        window = self._find_window(window_title)
        deadline = time.time() + 5
        while time.time() < deadline:
            for control in window.descendants():
                try:
                    text = control.window_text().strip()
                    ctrl_type = getattr(getattr(control, "element_info", None), "control_type", "")
                except Exception:
                    continue
                if (ctrl_type in ("Button", "Text", "MenuItem") and
                    ("Подтверд" in text or text == "Удалить" or "Удал" in text)):
                    self._log(f"delete_current_advertisement: найден popup, кликаю '{text}'.")
                    try:
                        self._click_best(control, allow_forbidden_text=True)
                    except RuntimeError:
                        control.click_input()
                    time.sleep(0.3)
                    return True
            time.sleep(0.3)
        return False

    def search_merchant(
        self,
        window_title: str,
        account_name: str,
        depth: int,
        stop_requested,
        on_progress,
    ) -> MerchantSearchResult:
        target_name = self._normalize_merchant_name(account_name)
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.SELL_URL):
            raise RuntimeError(f"Активная вкладка не является Sell USDT/RUB. Определён адрес: {current_url}.")

        on_progress(1, 0, "Возвращаюсь на первую страницу листинга")
        self._activate_first_search_page(window_title)
        for page in range(1, depth + 1):
            if stop_requested():
                return MerchantSearchResult(found=False)
            if page > 1:
                on_progress(page, 0, f"Открываю страницу {page}")
                page_control = self._find_page_control(window_title, page)
                self._click_best(page_control)
                time.sleep(0.2)
            on_progress(page, 0, f"Читаю продавцов на странице {page}")
            document = self._find_main_document(self._find_window(window_title))
            candidates = self._extract_merchant_candidates(document)
            candidates_text = ", ".join(candidates) if candidates else "список пуст"
            on_progress(page, 0, f"Страница {page}, список мерчантов: {candidates_text}")
            for index, candidate in enumerate(candidates, start=1):
                normalized_candidate = self._normalize_merchant_name(candidate)
                clean_name = re.sub(r"\s+", " ", re.sub(r"[^\w\s.-]+", " ", candidate, flags=re.UNICODE)).strip()
                on_progress(page, index, f"Проверяю продавца {index}/10: {clean_name}")
                if normalized_candidate == target_name:
                    on_progress(page, index, "Найден")
                    return MerchantSearchResult(found=True, page=page, position=index, matched_name=clean_name)
            if page < depth:
                on_progress(page, 0, f"Никнейм '{account_name}' не найден на странице {page}. Перехожу к следующей странице.")
            else:
                on_progress(page, 0, f"Никнейм '{account_name}' не найден на странице {page}.")
        return MerchantSearchResult(found=False)

    def collect_all_merchants(self, window_title: str, depth: int) -> list[str]:
        all_merchants: list[str] = []
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.SELL_URL):
            raise RuntimeError(f"Активная вкладка не является Sell USDT/RUB. Определён адрес: {current_url}.")

        self.open_url(window_title, self.SELL_URL)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                document = self._find_main_document(self._find_window(window_title))
                if self._document_contains_any_text(document, ("мерчант", "merchant")):
                    break
            except RuntimeError:
                pass
            time.sleep(0.5)

        self._activate_first_search_page(window_title)
        previous_candidates: list[str] | None = None

        for page in range(1, depth + 1):
            if page > 1:
                page_control = self._find_page_control(window_title, page)
                self._click_best(page_control)
                candidates = self._wait_for_merchant_page_candidates(window_title, previous_candidates)
            else:
                document = self._find_main_document(self._find_window(window_title))
                candidates = self._extract_merchant_candidates(document)
            all_merchants.extend(candidates)
            previous_candidates = candidates

        return all_merchants

    def _wait_for_merchant_page_candidates(
        self,
        window_title: str,
        previous_candidates: list[str] | None,
        timeout_seconds: float = 5.0,
    ) -> list[str]:
        deadline = time.time() + timeout_seconds
        latest_candidates: list[str] = []
        while time.time() < deadline:
            document = self._find_main_document(self._find_window(window_title))
            latest_candidates = self._extract_merchant_candidates(document)
            if latest_candidates and latest_candidates != previous_candidates:
                return latest_candidates
            time.sleep(0.2)
        return latest_candidates

    def read_current_sell_price(self, window_title: str) -> str:
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.SELL_URL):
            raise RuntimeError(
                f"Активная вкладка не является Sell USDT/RUB. Определён адрес: {current_url}."
            )
        price_pattern = re.compile(r"^\d+,\d{2}$")
        snippets: list[str] = []

        self.focus(window_title)
        send_keys("{HOME}")
        time.sleep(0.2)

        for _ in range(6):
            try:
                document = self._find_document_by_title_part(window, "P2P Crypto Trading")
            except RuntimeError:
                try:
                    document = self._find_main_document(window)
                except RuntimeError:
                    document = self._find_first_document(window)

            seen_sell_header = False
            items = self._interactive_items(document)
            for control in items:
                text = self._item_text(control)
                if not text:
                    continue
                text_lower = text.lower()
                if "цена" in text_lower:
                    seen_sell_header = True
                    continue
                if not seen_sell_header:
                    continue
                if price_pattern.match(text):
                    return text
                if text.endswith(" RUB"):
                    price_value = text.removesuffix(" RUB").strip()
                    if price_pattern.match(price_value):
                        return price_value

            snippets = [self._item_text(control) for control in items[:15]]
            self.focus(window_title)
            send_keys("{PGDN}")
            time.sleep(0.2)

        raise RuntimeError(
            "Не удалось прочитать цену на вкладке продажи USDT/RUB. "
            f"Текущий адрес: {current_url or 'не определён'}. Видимые элементы: {snippets}."
        )

    def open_standard_p2p_ad_form(self, window_title: str) -> None:
        window = self._find_window(window_title)
        current_url = self._read_current_url(window)
        if current_url and not self._url_matches(current_url, self.ADS_URL):
            raise RuntimeError(f"Активная вкладка не является Ads-страницей. Определён адрес: {current_url}.")

        self.focus(window_title)
        window = self._find_window(window_title)
        document = self._find_main_document(window)
        open_button = self._find_contains(document, text_part="Разместить", control_types=("Button", "Text"))
        if self._item_type(open_button) == "Button":
            open_button.click_input()
        else:
            self._click_best(open_button.parent() if self._item_type(open_button) == "Text" else open_button)
        time.sleep(0.35)

        popup_option = None
        popup_deadline = time.time() + 5
        while time.time() < popup_deadline:
            try:
                popup_option = self._find_contains(
                    self._find_window(window_title),
                    text_part="Стандартная P2P-торговля",
                    control_types=("Button", "Text", "ListItem", "Group"),
                )
                break
            except RuntimeError:
                time.sleep(0.2)
        if popup_option is None:
            raise RuntimeError("Не найден элемент, содержащий 'Стандартная P2P-торговля'.")
        self._click_best(popup_option.parent() if self._item_type(popup_option) == "Text" else popup_option)
        time.sleep(0.2)

        deadline = time.time() + 10
        while time.time() < deadline:
            document = self._find_main_document(self._find_window(window_title))
            if self._document_contains_any_text(document, ("Длительность оплаты", "Фиксированная", "Объявление")):
                return
            time.sleep(0.2)
        raise RuntimeError("Не удалось открыть форму создания объявления после выбора 'Стандартная P2P-торговля'.")

    def activate_sell_tab(self, window_title: str) -> None:
        self.ensure_sell_tab(window_title)

    def read_sell_price(self, window_title: str) -> str:
        return self.read_current_sell_price(window_title)

    def open_advertisement_form(self, window_title: str) -> None:
        self.open_standard_p2p_ad_form(window_title)

    def open_url(self, window_title: str, url: str) -> None:
        window = self._find_window(window_title)
        self.focus(window_title)
        address_bar = None
        for control in window.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if control_type == "Edit" and "bybit.com/" in title:
                address_bar = control
                break
        if address_bar is None:
            raise RuntimeError("Не удалось найти адресную строку браузера.")

        try:
            address_bar.iface_value.SetValue(url)
        except Exception:
            address_bar.click_input()
            send_keys("^a")
            time.sleep(0.2)
            send_keys(url, with_spaces=True)
        send_keys("{ENTER}")
        time.sleep(1.0)

    def _read_selected_trade_side(self, root) -> str | None:
        for control in self._interactive_items(root):
            text = self._item_text(control)
            if text.startswith("Покупка USDT"):
                return "Покупка"
            if text.startswith("Продажа USDT"):
                return "Продажа"
        return None

    def select_trade_side(self, window_title: str, trade_side: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        if self._read_selected_trade_side(document) == trade_side:
            return

        candidates: list[object] = []
        preferred_types = ("Button", "RadioButton", "ListItem", "Text")
        for control_type in preferred_types:
            for control in self._interactive_items(document):
                if self._item_text(control) == trade_side and self._item_type(control) == control_type:
                    candidates.append(control)

        if not candidates:
            raise RuntimeError(f"Не найден элемент '{trade_side}'.")

        verification_available = self._read_selected_trade_side(document) is not None
        last_selected_side = self._read_selected_trade_side(document)
        for candidate in candidates:
            self._click_best(candidate.parent() if self._item_type(candidate) == "Text" else candidate)
            time.sleep(0.2)
            document = self._find_main_document(self._find_window(window_title))
            last_selected_side = self._read_selected_trade_side(document)
            if last_selected_side == trade_side:
                return
            if not verification_available:
                return

        detected = last_selected_side or "не определён"
        raise RuntimeError(f"Не удалось переключить тип объявления на '{trade_side}'. Текущий тип: {detected}.")

    def set_fixed_price(self, window_title: str, price: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        control = self._find_edit_after_label(document, "Фиксированная")
        control.iface_value.SetValue(price)
        time.sleep(0.2)

    def set_payment_time(self, window_title: str, payment_time: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        items = self._interactive_items(document)
        group = None
        for index, control in enumerate(items):
            if self._item_text(control) != "Длительность оплаты":
                continue
            for next_control in items[index + 1 :]:
                next_text = self._item_text(next_control)
                next_type = self._item_type(next_control)
                if next_type == "Group":
                    group = next_control
                    break
                if next_text.endswith("мин."):
                    group = next_control.parent()
                    break
                if next_text:
                    break
            break
        if group is None:
            raise RuntimeError("Не удалось найти переключатель времени оплаты.")
        self._click_best(group)
        time.sleep(0.2)

        option_mark = "30мин." if payment_time.startswith("30") else "15мин."
        window = self._find_window(window_title)
        option = self._find_exact(window, title=option_mark, control_types=("Text", "ListItem"))
        self._click_best(option.parent() if self._item_type(option) == "Text" else option)
        time.sleep(0.2)

    def set_total_amount(self, window_title: str, total_amount: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        control = self._find_edit_after_label(document, "Общее количество")
        control.iface_value.SetValue(total_amount)
        time.sleep(0.2)

    def set_minimum_transaction(self, window_title: str, minimum_transaction: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        control = self._find_edit_after_label(document, "Мин. сумма транзакции")
        control.iface_value.SetValue(minimum_transaction)
        time.sleep(0.2)

    def set_maximum_transaction(self, window_title: str, maximum_transaction: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        control = self._find_edit_after_label(document, "Макс. сумма транзакции")
        control.iface_value.SetValue(maximum_transaction)
        time.sleep(0.2)

    def set_notes(self, window_title: str, notes: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        control = self._find_edit_after_label(document, "Примечания")
        control.iface_value.SetValue(notes)
        time.sleep(0.2)

    def ensure_counterparty_requirements(self, window_title: str, *, phone_linked: bool, email_linked: bool) -> None:
        if not phone_linked and not email_linked:
            return

        document = self._find_main_document(self._find_window(window_title))
        opener = self._find_contains(document, text_part="Добавить", control_types=("Text",))
        opener.parent().click_input()
        time.sleep(0.4)

        window = self._find_window(window_title)
        if phone_linked:
            phone_control = self._find_contains(window, text_part="Номер телефона", control_types=("CheckBox",))
            self._set_checkbox_state(phone_control, True)
        if email_linked:
            email_control = self._find_contains(window, text_part="электронной почты", control_types=("CheckBox",))
            self._set_checkbox_state(email_control, True)

        confirm = self._find_contains(window, text_part="Подтверд", control_types=("Button",))
        confirm.click_input()
        time.sleep(0.2)

    def ensure_payment_methods(self, window_title: str, methods: PaymentMethodState) -> None:
        requested = {
            "Bank Transfer": methods.bank_transfer,
            "Mobile Top-up": methods.mobile_top_up,
            "Cash Deposit to Bank": methods.cash_deposit,
        }
        wanted = {name for name, enabled in requested.items() if enabled}
        if not wanted:
            return

        document = self._find_main_document(self._find_window(window_title))
        current_methods = {
            self._item_text(control)
            for control in self._interactive_items(document)
            if self._item_text(control) in requested
        }
        if wanted.issubset(current_methods):
            return

        opener = self._find_contains(document, text_part="способами оплаты", control_types=("Button",))
        self.focus(window_title)
        self._click_best(opener)
        time.sleep(0.4)

        for name, enabled in requested.items():
            if not enabled:
                continue
            window = self._find_window(window_title)
            self._select_visible_payment_method(window, name)

        window = self._find_window(window_title)
        confirm = self._find_contains(window, text_part="Подтверд", control_types=("Button",))
        self._click_best(confirm)
        time.sleep(0.2)

    def accept_terms(self, window_title: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        checkbox = self._find_contains(
            document,
            text_part="Я прочитал(-а) и соглашаюсь",
            control_types=("CheckBox",),
        )
        self._set_checkbox_state(checkbox, True)

    def submit_advertisement(self, window_title: str) -> None:
        document = self._find_main_document(self._find_window(window_title))
        button = self._find_exact(document, title="Разместить объявления", control_types=("Button",))
        self._click_best(button)
        time.sleep(0.4)

    def enter_security_password(self, window_title: str, password: str) -> None:
        window = self._find_window(window_title)
        target = None
        deadline = time.time() + 10
        while time.time() < deadline:
            window = self._find_window(window_title)
            try:
                target = self._find_input_after_label(window, "Финансовый пароль")
            except RuntimeError:
                target = None
            if target is not None:
                break
            time.sleep(0.2)
        if target is None:
            raise RuntimeError("Не удалось найти поле финансового пароля в pop-up.")
        try:
            target.iface_value.SetValue(password)
        except (NoPatternInterfaceError, Exception):
            target.click_input()
            send_keys("^a")
            time.sleep(0.2)
            send_keys(password, with_spaces=True)
        time.sleep(0.2)
        confirm = None
        for control in window.descendants():
            try:
                title = control.window_text().strip()
                control_type = getattr(getattr(control, "element_info", None), "control_type", "")
            except Exception:
                continue
            if title == "Подтвердить" and control_type == "Button":
                confirm = control
                break
        if confirm is None:
            send_keys("{ENTER}")
        else:
            self._click_best(confirm)
        time.sleep(2.0)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
QUERY_FULL_PROCESS_IMAGE_NAME = KERNEL32.QueryFullProcessImageNameW
QUERY_FULL_PROCESS_IMAGE_NAME.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
QUERY_FULL_PROCESS_IMAGE_NAME.restype = wintypes.BOOL
OPEN_PROCESS = KERNEL32.OpenProcess
OPEN_PROCESS.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OPEN_PROCESS.restype = wintypes.HANDLE
CLOSE_HANDLE = KERNEL32.CloseHandle
CLOSE_HANDLE.argtypes = [wintypes.HANDLE]
CLOSE_HANDLE.restype = wintypes.BOOL


def get_process_image_path(process_id: int) -> str:
    handle = OPEN_PROCESS(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = QUERY_FULL_PROCESS_IMAGE_NAME(handle, 0, buffer, ctypes.byref(size))
        if not ok:
            return ""
        return buffer.value
    finally:
        CLOSE_HANDLE(handle)


