/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // add field
  collection.fields.addAt(9, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_1709638221",
    "hidden": false,
    "id": "relation1513686000",
    "maxSelect": 999,
    "minSelect": 0,
    "name": "inquiry",
    "presentable": false,
    "required": true,
    "system": false,
    "type": "relation"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // remove field
  collection.fields.removeById("relation1513686000")

  return app.save(collection)
})
