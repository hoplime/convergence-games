target "default" {
    secret = [
        { type = "file", id = "npmrc", src = "./.npmrc" },
    ]
    context = "."
    dockerfile = "Dockerfile"
    tags = [
        "jcheatley/waikato-rpg-convergence-games:latest",
    ]
    args = {
        BUILD_TIME = timestamp()
    }
}