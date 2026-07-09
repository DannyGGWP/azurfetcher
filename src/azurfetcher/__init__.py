import requests
import base64
import json
import random
import tomlkit
from pathlib import Path
from platformdirs import user_cache_dir
import questionary
import click
import tomlkit


# globals
APP_NAME = "azur_fetcher"
APP_VERSION = "0.1"

CACHE_DIR = Path(user_cache_dir(APP_NAME))


def get_config_path() -> Path:
    app_dir = click.get_app_dir(APP_NAME)
    config_dir = Path(app_dir)

    config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir / "config.toml"


def write_default_conf(path: Path):

    if path.exists():
        ans = click.prompt(
            f"Config File exists in {str(path)}! \nOverwrite? y/n", default="n"
        )
        if ans == "n":
            return

    doc = tomlkit.document()
    doc.add(tomlkit.comment("#######################################"))
    doc.add(tomlkit.comment("   Configuration for Azur Fetchr"))
    doc.add(tomlkit.comment("#######################################"))
    doc.add(tomlkit.nl())
    app = tomlkit.table()
    app.add("name", "Azur Fetchr")

    app.add("version", APP_VERSION)

    doc.add("app", app)
    cache = tomlkit.table()
    cache.add(tomlkit.comment("Manage data caching options. "))
    cache.add("dir", str(CACHE_DIR))

    cache.add("images", True)
    cache.add("voice_lines", True)
    doc.add("cache", cache)

    doc.add(tomlkit.nl())
    whitelist = tomlkit.table()
    whitelist.add("ships", [])
    whitelist["ships"].comment("Ship name to use for random selection")
    whitelist.add("skins", [])
    whitelist["skins"].comment(
        "Skin GIDs to use for random selection, Can work in conjunction with white list."
    )
    doc.add("whitelist", whitelist)

    doc.add(tomlkit.nl())

    blacklist = tomlkit.table()
    blacklist.add("ships", [])

    blacklist.add("skins", [])

    doc.add("blacklist", blacklist)

    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def read_config() -> dict:
    config_path = get_config_path()

    if not config_path.exists():
        write_default_conf(config_path)

    with open(config_path, "rb") as conf_file:
        config = tomlkit.parse(conf_file.read())
    return config


def write_config(conf):
    config_path = get_config_path()

    with open(config_path, "w", encoding="utf-8") as cf:
        cf.write(tomlkit.dumps(conf))


CONFIG = read_config()


def grab_ship_json():
    # check if the ship json exits.

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ship_json_file = CACHE_DIR / "ship_skin_list.json"

    if ship_json_file.exists():
        return True

    resp = requests.get(
        "https://raw.githubusercontent.com/Fernando2603/AzurLane/main/ship_skin_list.json"
    )
    if resp.status_code == 200:
        with open(ship_json_file, "wb") as file:
            file.write(resp.content)
    else:
        print("file not grabbed ")
        return False
    return True


def load_ship_json_file() -> dict:

    if not grab_ship_json():
        click.echo("Error grabing ship_skin_list.json")
        return {}

    p = CACHE_DIR / "ship_skin_list.json"
    data = []
    with open(p, "r") as ship_file:
        data = json.load(ship_file)
    ship_dict = {}
    for ship in data:
        ship_dict[ship["name"]] = ship
    return ship_dict


def display_image(image_data):
    print(f"\033_Ga=T,f=100;{image_data}\033\\")


def download_image(path: Path, url: str):
    with requests.get(url, stream=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as img_file:
            for chunk in resp.iter_content(chunk_size=8192):
                img_file.write(chunk)


def grab_skin_image_path(skin_gid, image_type, url) -> Path:

    # build the path
    skin_dir_path = CACHE_DIR / "skin" / str(skin_gid)
    skin_dir_path.mkdir(parents=True, exist_ok=True)

    img_path = skin_dir_path / f"{image_type}.png"
    if not img_path.exists():
        try:
            download_image(img_path, url)
        except requests.RequestException as e:
            click.echo(e, err=True)

    return img_path


@click.group()
@click.pass_context
def cli(ctx):
    pass


@cli.command()
@click.argument(
    "ship",
)
@click.option(
    "-t",
    "--picture-type",
    default="chibi",
    type=click.Choice(["chibi", "painting", "banner", "shipyard", "painting_n"]),
    help="grab a specific picture type. options are [chibi,painting,banner,shipyard,painting_n]",
)
@click.option("-d", "--display", is_flag=True, default=False)
def grab_ship(ship, picture_type, display):

    if not grab_ship_json():
        click.echo("Error grabing ship_skin_list.json")
        return

    ship_list = load_ship_json_file()
    if ship == "random" and CONFIG["whitelist"]["ships"] is not None:
        ship = random.choice(CONFIG["whitelist"]["ships"])
    elif ship == "random":
        ship = random.choice(list(ship_list))

    ship_data = ship_list.get(ship, "Bullin")
    ship_skins = ship_data["skins"]
    ship_skin = random.choice(ship_skins)
    if not ship_data:
        click.echo(
            click.style(f"Error fetching Ship: {ship}", fg="red"),
            err=True,
        )
        return

    # fall back logic
    if picture_type == "painting_n" and ship_skin[picture_type] is None:
        picture_type = "painting"

    if CONFIG["cache"]["images"]:
        # Image caching enabled so check to see if the image exits.
        img_path = grab_skin_image_path(
            ship_skin["id"],
            picture_type,
            ship_skin[picture_type],
        )
        if not display:
            click.echo(str(img_path))
            return
        with open(img_path, "rb") as imf:
            img_data = base64.b64encode(imf.read()).decode("ascii")
            display_image(img_data)
    else:
        resp = requests.get(ship_skin[picture_type])
        if resp.status_code == 200:
            image_data = base64.b64encode(resp.content).decode("ascii")
            display_image(image_data)
        else:
            click.echo(
                click.style(
                    f"Error fetching Ship: {ship}",
                    fg="red",
                ),
                err=True,
            )


def add_blacklist():

    if not grab_ship_json():
        click.echo("Error grabing ship_skin_list.json")
        return
    ship_json = load_ship_json_file()
    ship_choices = list(ship_json.keys())
    ship_name = questionary.autocomplete(
        "Select a Ship to add to the blacklist: ", choices=ship_choices
    ).ask()
    if ship_name:
        click.echo(
            f"Adding ship {ship_name} with GID:{
                ship_json[ship_name]['gid']
            } to blacklist"
        )
        CONFIG["blacklist"]["ships"].append(ship_name)
        write_config(CONFIG)
        click.echo(f"Black List Updated: {CONFIG['blacklist']['ships']}")


def add_whitelist():
    ship_json = load_ship_json_file()
    ship_choices = list(ship_json.keys())
    ship_name = questionary.autocomplete(
        "Select a Ship to add to the whitelist: ", choices=ship_choices
    ).ask()
    if ship_name:
        CONFIG["whitelist"]["ships"].append(ship_name)
        write_config(CONFIG)
        click.echo(f"White List Updated: {CONFIG['whitelist']['ships']}")


@cli.command()
@click.option(
    "-g",
    "--generate",
    is_flag=True,
    required=False,
    default=False,
    help="Generate a default Config file",
)
@click.option(
    "-b",
    "--blacklist",
    is_flag=True,
    help="add a ship to the blacklist",
)
@click.option(
    "-w",
    "--whitelist",
    is_flag=True,
    help="add a ship to the whitelist",
)
def config(generate, blacklist, whitelist):
    if generate:
        write_default_conf(get_config_path())

    if blacklist:
        add_blacklist()

    if whitelist:
        add_whitelist()
