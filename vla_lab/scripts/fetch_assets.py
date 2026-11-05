"""Download the Lightwheel USD assets of T1~T10 into ~/.cache/lightwheel_sdk, pinned to the versions the baseline used.

  ./vla_lab/fetch_assets.sh

No login is needed. Safe to re-run: what is already there is not downloaded again. An unpinned
request would fetch whatever is latest and could replace a cached scene.
"""
FLOORPLANS = {
    "1-1": "8915408f-2312-4f04-88be-546e720fbcd1",
    "2-2": "a5dad39c-fe52-407b-b4a1-c5e151faab61",
    "8-8": "ed73149f-b3a6-49e5-8871-33f7f47285e7",
}
OBJECTS = {
    "AlphabetSoup001": "a869d6d5-5b09-40b2-8f1a-e1e6150946b6",
    "Basket058": "271fddc3-4cc8-411b-86d5-1a027e46a872",
    "Bottle054": "39cf315d-6fe3-4e99-847d-8d6062313968",
    "Bowl008": "a52cd86d-61a4-467e-8df8-408e32e9f372",
    "Bowl009": "65130b0c-83b1-4f41-87ea-7695ff6c48a0",
    "Bowl011": "e1380449-a908-4547-8380-0e221644671c",
    "Butter001": "7769b163-cb0b-4745-a356-705230ef0425",
    "Cookies002": "4c1be0bf-65cb-4531-acb5-6e13e66e1a06",
    "CreamCheeseStick013": "08f6d939-5856-4ab8-a509-ad73972c8bbf",
    "Ketchup003": "fca215f0-5f2d-491f-87db-17dbda43c1e1",
    "MilkDrink009": "bb25f4c3-1afc-43d0-bdb4-4b4ffd52f675",
    "OrangeJuice001": "f021d614-0186-4e97-a0d0-9b0fe103eeba",
    "Plate012": "5e2234da-a84f-4883-b763-5c8e9268cddd",
}

if __name__ == "__main__":
    from lightwheel_sdk.loader import floorplan_loader, object_loader

    for name, version in FLOORPLANS.items():
        usd, _ = floorplan_loader.get_usd("libero", backend="robocasa", version=version)
        print("OK", name, usd, flush=True)
    for name, version in OBJECTS.items():
        usd, _, _ = object_loader.acquire_by_file_version(version)
        print("OK", name, usd, flush=True)
