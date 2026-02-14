# main.tf
resource "random_pet" "name" {
  length = 1
}

output "name" {
  value = random_pet.name.id
}
