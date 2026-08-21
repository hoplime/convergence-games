const scroll_button = (element_id: string) => {
    document.addEventListener('DOMContentLoaded', (_: Event) => {
        const button = document.getElementById(element_id);
        if (!button) {
            console.error(`Could not find ${element_id} element`);
            return;
        }
        // Create an observer that watches the nav element. When it scrolls
        // out of the viewport (by more than 200px), we unhide the scroll to
        // top button.
        const observer = new IntersectionObserver((entries: IntersectionObserverEntry[]) => {
            entries.forEach((entry: IntersectionObserverEntry) => {
                if (entry.isIntersecting) {
                    button.classList.add("hidden");
                } else {
                    button.classList.remove("hidden");
                }
            });
        }, {
            rootMargin: "200px"
        });
        observer.observe(document.getElementsByTagName("nav")[0]);

        button.addEventListener('click', () => {
            document.documentElement.scrollTo({
                top: 0,
                behavior: "smooth",
            });
        });
    });
}

export default scroll_button;