import os

from cmlibs.utils.zinc.field import create_field_finite_element, find_or_create_field_group
from cmlibs.utils.zinc.general import ChangeManager
from cmlibs.zinc.context import Context
from cmlibs.zinc.field import Field
from cmlibs.zinc.status import OK as ZINC_OK


class OpenCMISSPropagateFileReadFailed(Exception):
    pass


class PropagateZincDataModel(object):

    def __init__(self, settings):
        self._mesh_file = settings["mesh_file"]
        self._data_file = settings["data_file"]
        self._location = settings["location"]
        self._identifier = settings["identifier"]

        settings_dir = os.path.join(self._location, self._identifier + "-settings")
        if not os.path.isdir(settings_dir):
            os.mkdir(settings_dir)

        filename_parts = os.path.splitext(os.path.basename(self._mesh_file))
        self._output_file = os.path.join(settings_dir, filename_parts[0] + "_propagated.exf")

    def get_propagated_data_file(self):
        return self._output_file

    def done(self):
        c = Context("propagate")
        root_region = c.getDefaultRegion()

        # logger = c.getLogger()

        mesh_region = root_region.createChild("mesh")
        _read_file_into_region(self._mesh_file, mesh_region)
        data_region = root_region.createChild("data")
        _read_file_into_region(self._data_file, data_region)
        output_region = root_region.createChild("output")

        mesh_groups = _get_region_group_field_names(mesh_region)
        data_groups = _get_region_group_field_names(data_region)
        coordinate_fields = _get_region_coordinate_field_names(mesh_region)
        mesh_field_module = mesh_region.getFieldmodule()
        data_field_module = data_region.getFieldmodule()
        output_field_module = output_region.getFieldmodule()
        data_data_points = data_field_module.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_DATAPOINTS)
        output_data_points = output_field_module.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_DATAPOINTS)
        mesh_field_cache = mesh_field_module.createFieldcache()
        data_field_cache = data_field_module.createFieldcache()
        output_field_cache = output_field_module.createFieldcache()
        first_coordinate_field = mesh_field_module.findFieldByName(coordinate_fields[0])
        components_count = first_coordinate_field.getNumberOfComponents()
        mesh_mesh_3 = mesh_field_module.findMeshByDimension(3)

        for data_group in data_groups:
            if data_group in mesh_groups:
                mesh_group_field = mesh_field_module.findFieldByName(data_group).castGroup()
                element_group = mesh_group_field.getMeshGroup(mesh_mesh_3)
                element_iter = element_group.createElementiterator()
                element = element_iter.next()
                propagation_points = []
                while element.isValid():
                    mesh_field_cache.setMeshLocation(element, [0.5, 0.5, 0.5])
                    result, values = first_coordinate_field.evaluateReal(mesh_field_cache, components_count)
                    if result == ZINC_OK:
                        propagation_points.append(values)
                    element = element_iter.next()

                output_group_field = find_or_create_field_group(output_field_module, data_group)
                output_nodeset_group = output_group_field.getOrCreateNodesetGroup(output_data_points)
                data_group_field = data_field_module.findFieldByName(data_group).castGroup()
                data_nodeset_group = data_group_field.getNodesetGroup(data_data_points)
                node_iter = data_nodeset_group.createNodeiterator()
                node = node_iter.next()
                while node.isValid():

                    with ChangeManager(output_field_module):
                        node_template, source_field_names = _create_node_template_from_node(output_field_module, node)
                        output_coordinate_field = output_field_module.findFieldByName(first_coordinate_field.getName())
                        if not output_coordinate_field.isValid():
                            output_coordinate_field = _copy_field(output_field_module, first_coordinate_field)
                        node_template.defineField(output_coordinate_field)

                        source_field_values = []
                        for source_field_name in source_field_names:
                            source_field = data_field_module.findFieldByName(source_field_name)
                            data_field_cache.setNode(node)
                            result, value = source_field.evaluateReal(data_field_cache, source_field.getNumberOfComponents())
                            if result == ZINC_OK:
                                source_field_values.append(value)

                        for propagation_point in propagation_points:
                            output_node = output_data_points.createNode(-1, node_template)
                            output_nodeset_group.addNode(output_node)
                            output_field_cache.setNode(output_node)
                            # output_coordinate_field = output_field_module.findFieldByName(first_coordinate_field.getName())
                            result = output_coordinate_field.assignReal(output_field_cache, propagation_point)
                            for index, destination_field_name in enumerate(source_field_names):
                                output_field = output_field_module.findFieldByName(destination_field_name)
                                output_field.assignReal(output_field_cache, source_field_values[index])

                        node = node_iter.next()

        result = output_region.writeFile(self._output_file)
        return result == ZINC_OK


def print_log(logger):
    loggerMessageCount = logger.getNumberOfMessages()
    if loggerMessageCount > 0:
        for i in range(1, loggerMessageCount + 1):
            print(logger.getMessageTypeAtIndex(i), logger.getMessageTextAtIndex(i))
        logger.removeAllMessages()


def _copy_field(field_module, field):
    component_names = []
    for c in range(field.getNumberOfComponents()):
        component_name = field.getComponentName(c + 1)
        if component_name:
            component_names.append(component_name)

    component_names = component_names if component_names else None
    copied_field = create_field_finite_element(field_module, field.getName(), field.getNumberOfComponents(), managed=True, component_names=component_names)
    copied_field.setTypeCoordinate(field.isTypeCoordinate())
    return copied_field


def _create_node_template_from_node(field_module, node):
    data_points = field_module.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_DATAPOINTS)
    data_template = data_points.createNodetemplate()
    field_names = []
    node_nodeset = node.getNodeset()
    node_field_module = node_nodeset.getFieldmodule()
    node_data_points = node_field_module.findNodesetByFieldDomainType(Field.DOMAIN_TYPE_DATAPOINTS)
    node_template = node_data_points.createNodetemplate()
    node_field_cache = node_field_module.createFieldcache()
    node_field_cache.setNode(node)
    field_iter = node_field_module.createFielditerator()
    field = field_iter.next()
    while field.isValid():
        result = node_template.defineFieldFromNode(field, node)
        if result == ZINC_OK:
            new_field = field_module.findFieldByName(field.getName())
            if not new_field.isValid():
                new_field = _copy_field(field_module, field)

            data_template.defineField(new_field)
            field_names.append(field.getName())

        field = field_iter.next()

    return data_template, field_names


def _field_is_group(field):
    return field.castGroup().isValid()


def _field_is_probably_coordinate(field):
    finite_element_field = field.castFiniteElement()
    return field.getCoordinateSystemType() == Field.COORDINATE_SYSTEM_TYPE_RECTANGULAR_CARTESIAN and \
           field.getValueType() == Field.VALUE_TYPE_REAL and \
           field.getNumberOfComponents() <= 3 and \
           finite_element_field.isValid()


def _get_region_coordinate_field_names(region):
    return _get_region_field_names_conditional(region, _field_is_probably_coordinate)


def _get_region_group_field_names(region):
    return _get_region_field_names_conditional(region, _field_is_group)


def _get_region_field_names_conditional(region, condition):
    found_fields = []
    field_iter = region.getFieldmodule().createFielditerator()
    field = field_iter.next()
    while field.isValid():
        if condition(field):
            name = field.getName()
            found_fields.append(name)
        field = field_iter.next()

    return found_fields


def _read_file_into_region(filename, region):
    result = region.readFile(filename)
    if result != ZINC_OK:
        raise OpenCMISSPropagateFileReadFailed(f"Failed to read file '{filename}'")
