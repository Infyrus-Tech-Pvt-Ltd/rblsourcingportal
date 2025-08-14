/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1257430375")

  // remove field
  collection.fields.removeById("autodate4262580536")

  // remove field
  collection.fields.removeById("autodate2212487076")

  // add field
  collection.fields.addAt(2, new Field({
    "autogeneratePattern": "",
    "hidden": false,
    "id": "text4262580536",
    "max": 0,
    "min": 0,
    "name": "Name",
    "pattern": "",
    "presentable": false,
    "primaryKey": false,
    "required": false,
    "system": false,
    "type": "text"
  }))

  // add field
  collection.fields.addAt(3, new Field({
    "hidden": false,
    "id": "number2212487076",
    "max": null,
    "min": null,
    "name": "Contact",
    "onlyInt": false,
    "presentable": false,
    "required": false,
    "system": false,
    "type": "number"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1257430375")

  // add field
  collection.fields.addAt(2, new Field({
    "hidden": false,
    "id": "autodate4262580536",
    "name": "Name",
    "onCreate": true,
    "onUpdate": true,
    "presentable": false,
    "system": false,
    "type": "autodate"
  }))

  // add field
  collection.fields.addAt(3, new Field({
    "hidden": false,
    "id": "autodate2212487076",
    "name": "Contact",
    "onCreate": true,
    "onUpdate": true,
    "presentable": false,
    "system": false,
    "type": "autodate"
  }))

  // remove field
  collection.fields.removeById("text4262580536")

  // remove field
  collection.fields.removeById("number2212487076")

  return app.save(collection)
})
