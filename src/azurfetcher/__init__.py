import requests
import base64
import json
import random
import tomlkit
from pathlib import Path
from platformdirs import user_cache_dir
import questionary
import click
from term_image.image import from_file, from_url, Size

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
        ans = questionary.confirm(
            f"Config File exists in {str(path)}! \nOverwrite? y/n"
        ).ask()
        if not ans:
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
    whitelist["skins"].comment("Skin GIDs to use for random selection. Not use in V1.0")
    doc.add("whitelist", whitelist)

    doc.add(tomlkit.nl())

    blacklist = tomlkit.table()
    blacklist.comment("Not Used as of V0.1")
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
    # Grab a ship from the whitelist if this is random and the whitelist has entries
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
        else:
            img = from_file(img_path)
            img.draw()

    if display:
        img = from_url(ship_skin[picture_type])
        img.draw()
    else:
        click.echo(ship_skin[picture_type])


def add_blacklist():

    if not grab_ship_json():
        click.echo("Error grabing ship_skin_list.json")
        return
    ship_json = load_ship_json_file()
    ship_choices = list(ship_json.keys())
    ship_name = questionary.autocomplete(
        "Select a Ship to add to the blacklist: ",
        choices=ship_choices,
        validate=lambda choice: (
            True if choice in ship_choices else "Please Enter a Full ship Name"
        ),
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
        repeat = questionary.confirm("Would you like to add another ship?").ask()
        if repeat:
            add_blacklist()


def add_whitelist():
    ship_json = load_ship_json_file()
    ship_choices = list(ship_json.keys())
    ship_name = questionary.autocomplete(
        "Select a Ship to add to the whitelist: ",
        choices=ship_choices,
        validate=lambda choice: (
            True if choice in ship_choices else "Please Enter a Full ship Name"
        ),
    ).ask()
    if ship_name:
        CONFIG["whitelist"]["ships"].append(ship_name)
        write_config(CONFIG)
        click.echo(f"White List Updated: {CONFIG['whitelist']['ships']}")
        repeat = questionary.confirm("Would you like to add another ship?").ask()
        if repeat:
            add_whitelist()


def remove_whitelist():
    ship_choices = CONFIG["whitelist"]["ships"]
    if ship_choices is None:
        click.echo("No ships on list")
        return

    ship_name = questionary.select(
        "Select a Ship to add to remove from the whitelist: ",
        choices=ship_choices,
    ).ask()
    if ship_name:
        CONFIG["whitelist"]["ships"].remove(ship_name)
        write_config(CONFIG)
        click.echo(f"White List Updated: {CONFIG['whitelist']['ships']}")
        repeat = questionary.confirm("Would you like to remove another ship?").ask()
        if repeat:
            remove_whitelist()


def remove_blacklist():
    ship_choices = CONFIG["blacklist"]["ships"]
    if ship_choices is None or len(ship_choices) == 0:
        click.echo("No ships on list")
        return
    ship_name = questionary.select(
        "Select a Ship to add to remove from the blacklist: ",
        choices=ship_choices,
    ).ask()
    if ship_name:
        CONFIG["blacklist"]["ships"].remove(ship_name)
        write_config(CONFIG)
        click.echo(f"White List Updated: {CONFIG['blacklist']['ships']}")
        repeat = questionary.confirm("Would you like to remove another ship?").ask()
        if repeat:
            remove_blacklist()


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
@click.option(
    "-r",
    "--remove",
    is_flag=True,
    help="used with whitelist or blacklist flags to remove ships from the list",
)
@click.option("-p", "--print", is_flag=True)
def config(generate, blacklist, whitelist, print, remove):
    if generate:
        write_default_conf(get_config_path())

    if blacklist and not remove:
        add_blacklist()
    elif blacklist and remove:
        remove_blacklist()

    if whitelist and not remove:
        add_whitelist()
    elif whitelist and remove:
        remove_whitelist()
    if print:
        click.echo(CONFIG)
