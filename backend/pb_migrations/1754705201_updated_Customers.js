/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // add field
  collection.fields.addAt(7, new Field({
    "hidden": false,
    "id": "bool567631544",
    "name": "List_Rule",
    "presentable": false,
    "required": true,
    "system": false,
    "type": "bool"
  }))

  // add field
  collection.fields.addAt(8, new Field({
    "hidden": false,
    "id": "bool2594262285",
    "name": "View_Rule",
    "presentable": false,
    "required": true,
    "system": false,
    "type": "bool"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // remove field
  collection.fields.removeById("bool567631544")

  // remove field
  collection.fields.removeById("bool2594262285")

  return app.save(collection)
})
