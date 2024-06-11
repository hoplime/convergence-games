from fastui import FastUI
from fastui import components as c
from fastui.events import GoToEvent


def page(*components: list[c.AnyComponent], title: str | None = None) -> FastUI:
    return [
        c.PageTitle(text=f"Convergence - {title}" if title else "Convergence"),
        c.Navbar(
            title="Convergence",
            title_event=GoToEvent(url="/"),
            start_links=[
                c.Link(
                    components=[c.Text(text="Games")],
                    on_click=GoToEvent(url="/games"),
                    active="startswith:/games",
                ),
                c.Link(
                    components=[c.Text(text="Sessions")],
                    on_click=GoToEvent(url="/sessions"),
                    active="startswith:/sessions",
                ),
            ],
        ),
        c.Page(
            components=[
                *((c.Heading(text=title),) if title else ()),
                *components,
            ],
        ),
        c.Footer(extra_text="Footer", links=[]),
    ]
