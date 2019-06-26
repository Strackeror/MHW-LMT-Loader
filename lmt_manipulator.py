import sys
import json
from lmt import Lmt

def events_to_json(events):
    events_dict = { "unkn": events.unkn } 
    categories = []
    for category in events.categories:
        category_dict = {"type":category.type}
        events = []
        for event in category.events:
            event_dict = {
                "type":event.type,
                "buffer":[]
            }
            for buffer in event.buffer:
                event_dict["buffer"] += [buffer.values]
            events += [event_dict]
        category_dict["events"] = events
        categories += [category_dict]
    events_dict["categories"] = categories
    return json.dumps(events_dict, indent=True)

def json_to_events(json_str):
    events_dict = json.loads(json_str)
    events = Lmt.Events(unkn = events_dict["unkn"], categories_offset = 0, category_count = 0)
    events.categories = []
    for category_dict in events_dict["categories"]:
        category = Lmt.Events.Event(type=category_dict["type"], offset = 0, count = 0)
        category.events =  []
        for event_dict in category_dict["events"]:
            event = Lmt.Events.Event(type=event_dict["type"], offset = 0, count = 0)
            event.buffer = []
            for buffer in event_dict["buffer"]:
                event.buffer += [Lmt.Events.Data(values = buffer)]
            category.events += [event]
        events.categories += [category]
    return events

def export_animation(params):
    if len(params) < 2:
        return
    path = params[0]
    id = int(params[1])
    output_path = "%s.%03d.lmta" % (path, id)
    if len(params) >= 3:
        output_path = params[2]

    lmt_file = open(path, 'rb')
    lmt = Lmt.LMT(lmt_file)
    animation = lmt.get_animation(id)

    output_file = open(output_path, 'wb')
    output_file.write(animation.serialize(0))

def override_animation(params):
    if len(params) < 3:
        return
    path = params[0]
    lmt_path = params[1]
    id = int(params[2])

    lmt_file = open(lmt_path, 'rb')
    lmt = Lmt.LMT(lmt_file)

    input_file = open(path, 'rb')
    animation = Lmt.AnimationBlock(input_file)
    lmt.override_animation(id, animation)

    lmt_file = open(lmt_path, 'wb')
    lmt_file.write(lmt.serialize())
    
def export_events(params):
    if len(params) < 2:
        return
    path = params[0]
    output_path = params[1]

    animation = Lmt.AnimationBlock(open(path, 'rb'))
    open(output_path, 'w').write(events_to_json(animation.events))
   
def import_events(params):
    if len(params) < 2:
        return
    path = params[0]
    output_path = params[1]

    animation = Lmt.AnimationBlock(open(output_path, 'rb'))
    animation.events = json_to_events(open(path, 'r').read())
    open(output_path, 'wb').write(animation.serialize(0))

if __name__ == "__main__":
    if (len(sys.argv) < 2):
        exit()
    {
        "export_animation":export_animation,
        "override_animation":override_animation,
        "export_events":export_events,
        "import_events":import_events
    }[sys.argv[1]](sys.argv[2:])