/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1257430375")

  // update collection data
  unmarshal({
    "name": "Suppliers"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1257430375")

  // update collection data
  unmarshal({
    "name": "suppliers"
  }, collection)

  return app.save(collection)
})
